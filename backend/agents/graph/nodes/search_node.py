"""
Search Node — hybrid retrieval with structured sort detection.

Two-tier sort intent detection:
  1. Regex fast path: 12 patterns covering ~90% of sort queries (0ms)
  2. LLM fallback: when regex misses, ask LLM to extract sort intent (~20ms, cached 5min)

When a sort intent is detected, bypasses FAISS entirely and uses SQL ORDER BY.
The SearchPlan is stored in state for trace/observability.
"""

import re
import time
from functools import lru_cache

from ..state import AgentState, NodeTrace, ProductRef, DocRef
from ..contracts.search_plan import (
    SearchPlan,
    QueryIntent,
    RetrievalStrategy,
    SORT_PATTERNS,
    VALID_SORT_FIELDS,
    VALID_DIRECTIONS,
    normalize_query,
)
from ..cost_router import CostRouter, estimate_tokens
from ..rag.retriever import get_retriever

# ── Regex-based sort detection ─────────────────────────────────

def _regex_detect(query: str) -> SearchPlan | None:
    """Try to detect sort intent via regex patterns."""
    for pattern, sort_by, direction in SORT_PATTERNS:
        if re.search(pattern, query):
            return SearchPlan(
                strategy=RetrievalStrategy.STRUCTURED_SORT,
                sort_by=sort_by,
                direction=direction,
                semantic_query=normalize_query(query),
                method="regex",
                detail=f"Pattern matched: {pattern[:40]}...",
            )
    return None


# ── LLM fallback ───────────────────────────────────────────────

SORT_LLM_PROMPT = """Extract sort intent from this query. Return ONLY a JSON object.

Valid sort_by values: price, created_at, popularity, rating
Valid direction values: asc, desc
If no sort intent, return null for both.

Query: "{query}"

Return: {{"sort_by": "price"|"created_at"|"popularity"|"rating"|null, "direction": "asc"|"desc"|null}}"""


@lru_cache(maxsize=256)
def _llm_detect_cached(normalized: str) -> SearchPlan | None:
    """LLM-based sort detection, cached by normalized query."""
    try:
        from agents.core.llm_client import get_llm_client
        prompt = SORT_LLM_PROMPT.format(query=normalized)
        response = get_llm_client().chat(prompt, max_tokens=50)
        text = response.text.strip()

        import json
        # Extract JSON from possible markdown fence
        match = re.search(r'\{[^}]+\}', text)
        if match:
            data = json.loads(match.group(0))
            sort_by = data.get("sort_by")
            direction = data.get("direction")
            if sort_by in VALID_SORT_FIELDS and direction in VALID_DIRECTIONS:
                return SearchPlan(
                    strategy=RetrievalStrategy.STRUCTURED_SORT,
                    sort_by=sort_by,
                    direction=direction,
                    semantic_query=normalized,
                    method="llm",
                    detail=f"LLM extracted: {sort_by} {direction}",
                )
    except Exception:
        pass
    return None


def detect_sort_intent(query: str) -> SearchPlan:
    """Two-tier sort intent detection: regex → LLM fallback.

    Returns a SearchPlan. If no sort intent detected, returns a
    semantic SearchPlan (strategy=semantic).
    """
    # Tier 1: regex
    plan = _regex_detect(query)
    if plan:
        return plan

    # Tier 2: LLM (cached by normalized query)
    normalized = normalize_query(query)
    plan = _llm_detect_cached(normalized)
    if plan:
        return plan

    # No sort intent → default to semantic
    return SearchPlan(
        strategy=RetrievalStrategy.SEMANTIC,
        semantic_query=normalized,
        method="none",
        detail="No sort intent detected, using semantic search",
    )


# ── Structured sort execution ──────────────────────────────────

def _execute_structured_sort(plan: SearchPlan, limit: int = 10) -> list[ProductRef]:
    """Execute SQL ORDER BY for structured sort queries."""
    import django
    django.setup()
    from products.models import Product

    sort_field = plan.sort_by or "price"
    direction = plan.direction or "desc"
    order_prefix = "-" if direction == "desc" else ""

    # Map logical fields to real DB fields / annotations
    ANNOTATION_FIELDS = {
        "popularity": "_sold_count",
        "rating": "_average_rating",
    }
    actual_field = ANNOTATION_FIELDS.get(sort_field, sort_field)

    qs = Product.objects.filter(is_active=True)

    # ── Apply category filter ──
    if plan.category_filter:
        qs = qs.filter(category__name__icontains=plan.category_filter)

    # ── Apply budget band as price filter ──
    if plan.budget_band:
        if plan.budget_band == "0-500":
            qs = qs.filter(price__lte=500)
        elif plan.budget_band == "500-1500":
            qs = qs.filter(price__gte=500, price__lte=1500)
        elif plan.budget_band == "1500+":
            qs = qs.filter(price__gte=1500)

    # Fields that need .with_sales_data() annotation
    if sort_field in ANNOTATION_FIELDS:
        qs = qs.with_sales_data()

    products = qs.order_by(f"{order_prefix}{actual_field}")[:limit]

    refs = []
    for p in products:
        refs.append(ProductRef(
            id=p.id,
            name=p.name,
            price=float(p.price),
            category=p.category.name if p.category else "",
            relevance=1.0,
        ))
    return refs


# ── Main Node ──────────────────────────────────────────────────

def search_node(state: AgentState) -> AgentState:
    """Hybrid retrieval driven by SearchPlan from ConstraintParser."""

    start = time.time()

    query = state.user_query or ""
    normalized = normalize_query(query)

    # ── Load SearchPlan from orchestrator (ConstraintParser) ──
    plan_dict = state.parallel_results.get("_search_plan", {})
    plan = SearchPlan(
        intent=plan_dict.get("intent", QueryIntent.RECOMMEND),
        sort_by=plan_dict.get("sort_by"),
        direction=plan_dict.get("direction"),
        category_filter=plan_dict.get("category_filter"),
        budget_band=plan_dict.get("budget_band"),
        strategy=plan_dict.get("strategy", RetrievalStrategy.SEMANTIC),
        semantic_query=normalized,
        method=plan_dict.get("method", "regex"),
        detail=plan_dict.get("detail", ""),
    )

    # ── Enrich with memory context ──
    enriched_query = query
    if state.user_memory and state.user_memory.preferences:
        top_prefs = sorted(
            state.user_memory.preferences.items(),
            key=lambda x: x[1], reverse=True
        )[:3]
        pref_ctx = " ".join(f"{cat}" for cat, _ in top_prefs)
        enriched_query = f"{query} {pref_ctx}"

    if plan.is_structured():
        # ── Structured sort path: SQL ORDER BY ──
        top_k = state.parallel_results.get("search_top_k", 10)
        products = _execute_structured_sort(plan, limit=top_k)
        docs: list[DocRef] = []

        state.retrieved_products = products
        state.retrieved_docs = docs
        state.tool_results["products"] = [
            {"product_id": p.id, "product_name": p.name, "name": p.name,
             "price": str(p.price), "category_name": p.category,
             "score": p.relevance}
            for p in products
        ]
        state.current_node = "search"
        method_label = plan.method.upper() if plan.method == "llm" else "快速匹配"
        budget_info = f" · 预算 {plan.budget_band}" if plan.budget_band else ""
        state.ui_message = (
            f"已识别排序意图（{method_label}），"
            f"按 {plan.sort_by} {plan.direction.upper()} 排序{budget_info}"
        )
        state.steps_done.append("search")

        # Add search plan phase info
        phase = plan.to_phase()
        state.parallel_results["_search_phase_detail"] = phase.get("detail", "")
        state.parallel_results["_search_phase_label"] = phase.get("label", "")

    else:
        # ── Semantic path: FAISS + SQL LIKE → RRF ──
        retriever = get_retriever()
        top_k = state.parallel_results.get("search_top_k", 10)
        products, docs = retriever.search(
            enriched_query,
            top_k=top_k,
            user_id=state.user_id,
        )

        state.retrieved_products = products
        state.retrieved_docs = docs
        # Store as dicts for block rendering
        state.tool_results["products"] = [
            {"product_id": p.id, "product_name": p.name, "name": p.name,
             "price": str(p.price), "category_name": p.category,
             "score": p.relevance}
            for p in products
        ]
        state.current_node = "search"
        state.ui_message = f"正在搜索：{query}"
        state.steps_done.append("search")

        state.parallel_results["_search_phase_detail"] = "FAISS + MySQL LIKE → RRF融合"
        state.parallel_results["_search_phase_label"] = "语义检索"

    latency = int((time.time() - start) * 1000)

    state.trace.append(NodeTrace(
        node_name="search",
        model_name="" if plan.is_structured() else "all-MiniLM-L6-v2",
        latency_ms=latency,
    ))

    return state
