"""
Search Node — P1 strategy-driven hybrid retrieval.

Upgrades the old binary "structured? → SQL : FAISS" to a 3-strategy system:
  SQL_ONLY  — Direct SQL ORDER BY for clear sort intents
  SEMANTIC  — FAISS vector search + RRF fusion
  HYBRID    — Both paths, unified ranking in search_node (Phase 6: no merge_node)

Strategy is selected by SearchStrategySelector, not by parser alone.
"""

import re
import time
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

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
        logger.warning("LLM sort detection failed, falling back", exc_info=True)
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
    from agents.commerce.queries.product_query import ProductQuery

    sort_field = plan.sort_by or "price"
    direction = plan.direction or "desc"
    order_prefix = "-" if direction == "desc" else ""

    # Map logical fields to real DB fields / annotations
    ANNOTATION_FIELDS = {
        "popularity": "_sold_count",
        "rating": "_average_rating",
    }
    actual_field = ANNOTATION_FIELDS.get(sort_field, sort_field)

    qs = ProductQuery.purchasable()

    # Apply category filter
    if plan.category_filter:
        qs = qs.filter(category__name__icontains=plan.category_filter)

    # Apply budget band as price filter
    if plan.budget_band:
        if plan.budget_band == "0-500":
            qs = qs.filter(price__lte=500)
        elif plan.budget_band == "500-1500":
            qs = qs.filter(price__gte=500, price__lte=1500)
        elif plan.budget_band == "1500+":
            qs = qs.filter(price__gte=1500)
        elif plan.budget_band == "500+":
            qs = qs.filter(price__gte=500)
        elif plan.budget_band == "0+":
            pass  # no lower bound filter — match all

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
    """P1 strategy-driven hybrid retrieval.

    Uses SearchStrategySelector to decide SQL_ONLY / SEMANTIC / HYBRID.
    HYBRID mode produces both structured and semantic results for merge_node.
    """
    import django
    django.setup()

    # ── Fast path: resolved product reference (VIEW_DETAIL only) ──
    resolved_ref = state.parallel_results.get("_resolved_ref")
    if resolved_ref is not None:
        from agents.graph.routing.reference_resolver import ReferenceAction
        if resolved_ref.action == ReferenceAction.VIEW_DETAIL:
            import django as _django_fp
            _django_fp.setup()
            from agents.commerce.queries.product_query import ProductQuery
            try:
                p = ProductQuery.purchasable().get(id=resolved_ref.target.product_ids[0])
                pr = ProductRef(
                    id=p.id, name=p.name, price=float(p.price or 0),
                    category=p.category.name if p.category else "",
                    relevance=1.0,
                )
                state.retrieved_products = [pr]
                state.tool_results["products"] = [{
                    "product_id": p.id, "product_name": p.name, "name": p.name,
                    "price": str(p.price), "category_name": p.category.name if p.category else "",
                    "score": 1.0,
                }]
                state.current_node = "search"
                state.steps_done.append("search")
                state.ui_message = f"已选择：{p.name}"
                state.parallel_results["_search_phase_label"] = "引用详情"
                state.parallel_results["_search_phase_detail"] = f"查看商品：{p.name}"
                return state
            except Exception:
                logger.warning("VIEW_DETAIL fast path failed for product_ids=%s", resolved_ref.target.product_ids)

    start = time.time()

    query = state.user_query or ""
    normalized = normalize_query(query)

    # ── Resolve retrieval mode ──
    mode = _resolve_mode(state.intent)
    state.parallel_results["_retrieval_mode"] = mode

    # ── Load SearchPlan from orchestrator (ConstraintParser + Validator) ──
    plan_dict = state.parallel_results.get("_search_plan", {})
    plan = SearchPlan(
        intent=plan_dict.get("intent", QueryIntent.RECOMMEND),
        sort_by=plan_dict.get("sort_by"),
        direction=plan_dict.get("direction"),
        category_filter=plan_dict.get("category_filter"),
        brand=plan_dict.get("brand"),
        budget_lower=plan_dict.get("budget_lower"),
        budget_upper=plan_dict.get("budget_upper"),
        budget_band=plan_dict.get("budget_band"),
        strategy=plan_dict.get("strategy", RetrievalStrategy.SEMANTIC),
        semantic_query=normalized,
        method=plan_dict.get("method", "regex"),
        detail=plan_dict.get("detail", ""),
    )

    # ── SQL constraint filter (brand + price range) ─────────────
    brand_filter = plan_dict.get("brand")
    budget_lower = plan_dict.get("budget_lower")
    budget_upper = plan_dict.get("budget_upper")
    category_filter = plan_dict.get("category_filter")

    sql_ids = None
    if brand_filter or budget_lower is not None or budget_upper is not None or category_filter:
        from agents.commerce.queries.product_query import ProductQuery as _PQ
        qs = _PQ.purchasable()
        if category_filter:
            qs = qs.filter(category__name__icontains=category_filter)
        if brand_filter:
            qs = qs.filter(brand__iexact=brand_filter)
        if budget_lower is not None:
            qs = qs.filter(price__gte=budget_lower)
        if budget_upper is not None:
            qs = qs.filter(price__lte=budget_upper)
        sql_ids = set(qs.values_list('id', flat=True)[:200])

    # ── P1: Strategy Selection ───────────────────────────────
    _commerce_conf = state.confidence if state.confidence > 0 else 0.5
    _active_signals = 0
    if state.user_id:
        try:
            from ..feedback.signal_store import signal_count
            _active_signals = signal_count(state.user_id)
        except Exception:
            logger.warning("Signal count query failed for user=%s", state.user_id, exc_info=True)

    from ..search_strategy_selector import select as select_strategy, SearchStrategy
    strategy_dec = select_strategy(
        plan=plan,
        commerce_confidence=_commerce_conf,
        active_signals=_active_signals,
        query=query,
    )

    # Store for DecisionTrace + merge_node
    state.parallel_results["_search_strategy"] = strategy_dec.strategy
    state.parallel_results["_search_strategy_decision"] = strategy_dec.to_dict()

    # Enrich with memory context for semantic path
    enriched_query = query
    if state.user_memory and state.user_memory.preferences:
        top_prefs = sorted(
            state.user_memory.preferences.items(),
            key=lambda x: x[1], reverse=True
        )[:3]
        pref_ctx = " ".join(f"{cat}" for cat, _ in top_prefs)
        enriched_query = f"{query} {pref_ctx}"

    # ── Execute based on strategy ────────────────────────────
    products: list[ProductRef] = []
    docs: list[DocRef] = []
    structured_products: list[ProductRef] = []

    top_k = state.parallel_results.get("search_top_k", 10)

    # Structured path (SQL_ONLY or HYBRID)
    if strategy_dec.strategy in (SearchStrategy.SQL_ONLY, SearchStrategy.HYBRID):
        if plan.is_structured():
            structured_products = _execute_structured_sort(plan, limit=top_k)
            # Apply SQL constraint filter to structured results
            if sql_ids is not None:
                structured_products = [p for p in structured_products if p.id in sql_ids]

    # Semantic path (SEMANTIC or HYBRID)
    if strategy_dec.strategy in (SearchStrategy.SEMANTIC, SearchStrategy.HYBRID):
        retriever = get_retriever()
        products, docs = retriever.search(
            enriched_query,
            top_k=top_k,
            user_id=state.user_id,
        )
        # ── Apply SQL constraint filter (FAISS∩SQL merge) ──
        all_faiss_products = list(products)
        if sql_ids is not None:
            products = [p for p in products if p.id in sql_ids]
        # ── Constraint relaxation when FAISS∩SQL is empty ──
        relaxed_constraints = []
        if not products and sql_ids is not None:
            # Re-fetch with larger window to get more candidates
            products_large, _ = retriever.search(enriched_query, top_k=100, user_id=state.user_id)
            all_faiss_products = list(products_large)
            from agents.commerce.queries.product_query import ProductQuery as _PQ
            
            # Layer 1: drop brand (keep category + price)
            if brand_filter:
                qs1 = _PQ.purchasable()
                if category_filter:
                    qs1 = qs1.filter(category__name__icontains=category_filter)
                if budget_lower is not None:
                    qs1 = qs1.filter(price__gte=budget_lower)
                if budget_upper is not None:
                    qs1 = qs1.filter(price__lte=budget_upper)
                relaxed_ids = set(qs1.values_list('id', flat=True)[:200])
                if relaxed_ids:
                    products = [p for p in all_faiss_products if p.id in relaxed_ids]
                    if products:
                        relaxed_constraints.append(f"品牌「{brand_filter}」")
            
            # Layer 2: also drop rating (keep only category + price)
            if not products and (brand_filter or category_filter):
                qs2 = _PQ.purchasable()
                if category_filter:
                    qs2 = qs2.filter(category__name__icontains=category_filter)
                if budget_lower is not None:
                    qs2 = qs2.filter(price__gte=budget_lower)
                if budget_upper is not None:
                    qs2 = qs2.filter(price__lte=budget_upper)
                relaxed_ids = set(qs2.values_list('id', flat=True)[:200])
                if relaxed_ids:
                    products = [p for p in all_faiss_products if p.id in relaxed_ids]
                    if products and not relaxed_constraints:
                        if brand_filter:
                            relaxed_constraints.append(f"品牌「{brand_filter}」")
            
            if relaxed_constraints:
                state.parallel_results["_relaxed_constraints"] = relaxed_constraints
            if not products:
                # Layer 3: pure semantic fallback — no SQL constraints
                products = [p for p in all_faiss_products]
                if products:
                    relaxed_constraints.append("全部筛选条件")
                    state.parallel_results["_relaxed_constraints"] = relaxed_constraints
                else:
                    state.parallel_results["_no_results"] = True
        # ── Enrich from DB + weighted ranking ──
        products, score_breakdown = _enrich_and_rank(products, plan_dict, state, top_k, skip_diversity=bool(brand_filter) or mode == "exact")
        if score_breakdown:
            state.parallel_results["_score_breakdown"] = score_breakdown
    elif strategy_dec.strategy == SearchStrategy.SQL_ONLY:
        products = structured_products
        docs = []
        products, score_breakdown = _enrich_and_rank(products, plan_dict, state, top_k, skip_diversity=bool(brand_filter) or mode == "exact")
        if score_breakdown:
            state.parallel_results["_score_breakdown"] = score_breakdown

    # ── Store results ────────────────────────────────────────
    state.retrieved_products = products

    # Build DocRef from Product DB fields (Product RAG)
    docs = _build_doc_refs(products)
    state.retrieved_docs = docs

    # For HYBRID: store structured results separately for merge_node
    if strategy_dec.strategy == SearchStrategy.HYBRID and structured_products:
        state.parallel_results["_structured_products"] = [
            {"product_id": p.id, "product_name": p.name, "name": p.name,
             "price": str(p.price), "category_name": p.category,
             "score": p.relevance}
            for p in structured_products
        ]

    # Build product dicts for UI (merge both in HYBRID mode)
    all_products = list(products)
    if strategy_dec.strategy == SearchStrategy.HYBRID:
        all_products = list(structured_products) + list(products)

    state.tool_results["products"] = [
        {"product_id": p.id, "product_name": p.name, "name": p.name,
         "price": str(p.price), "category_name": p.category,
         "score": p.relevance}
        for p in all_products
    ]
    state.current_node = "search"

    # ── UI message ───────────────────────────────────────────
    if strategy_dec.strategy == SearchStrategy.SQL_ONLY:
        method_label = plan.method.upper() if plan.method == "llm" else "快速匹配"
        budget_info = f" · 预算 {plan.budget_band}" if plan.budget_band else ""
        state.ui_message = (
            f"已识别排序意图（{method_label}），"
            f"按 {plan.sort_by} {plan.direction.upper()} 排序{budget_info}"
        )
    elif strategy_dec.strategy == SearchStrategy.HYBRID:
        state.ui_message = (
            f"混合检索：SQL排序({len(structured_products)}条) + 语义({len(products)}条)"
        )
    else:
        state.ui_message = f"正在搜索：{query}"

    state.steps_done.append("search")

    # ── Trace metadata ───────────────────────────────────────
    phase = plan.to_phase()
    if strategy_dec.strategy == SearchStrategy.HYBRID:
        phase = {"phase": "searching", "label": "混合检索",
                 "detail": "SQL + FAISS → merge_node融合"}
    state.parallel_results["_search_phase_detail"] = phase.get("detail", "")
    state.parallel_results["_search_phase_label"] = phase.get("label", "")

    latency = int((time.time() - start) * 1000)

    state.trace.append(NodeTrace(
        node_name="search",
        model_name="" if plan.is_structured() else "paraphrase-multilingual-MiniLM-L12-v2",
        latency_ms=latency,
    ))

    return state


def _build_doc_refs(products: list[ProductRef]) -> list[DocRef]:
    """Build DocRef with full product specs from DB for RAG context injection."""
    if not products:
        return []

    import django
    django.setup()
    from products.models import Product

    docs: list[DocRef] = []
    product_ids = [p.id for p in products]
    db_products = {
        p.id: p
        for p in Product.objects.filter(id__in=product_ids)
    }

    for p in products:
        detail_parts = [f"{p.name} | ¥{p.price}"]
        db_p = db_products.get(p.id)
        if db_p:
            if db_p.battery_life:
                detail_parts.append(f"续航{db_p.battery_life}h")
            if db_p.bluetooth_version:
                detail_parts.append(f"蓝牙{db_p.bluetooth_version}")
            if db_p.noise_cancellation:
                detail_parts.append("主动降噪")
            if db_p.weight:
                detail_parts.append(f"{db_p.weight}g")
            if db_p.specs:
                for k, v in db_p.specs.items():
                    detail_parts.append(f"{k}:{v}")
        docs.append(DocRef(
            id=str(p.id),
            content=" | ".join(detail_parts),
            relevance=p.relevance,
        ))

    return docs


def _enrich_and_rank(products, plan_dict, state, top_k, skip_diversity=False):
    """Enrich FAISS results with DB data, rank, convert to ProductRef."""
    if not products:
        return [], []
    from products.models import Product as _Product
    pids = [p.id for p in products]
    db_products = {p.id: p for p in _Product.objects.filter(id__in=pids)}
    enriched = []
    for p in products:
        dbp = db_products.get(p.id)
        if dbp:
            dbp.relevance = p.relevance
            enriched.append(dbp)
    if not enriched:
        return products, None
    enriched, score_breakdown = _rank_products(enriched, plan_dict, top_k, skip_diversity)
    products = [
        ProductRef(
            id=p.id, name=p.name, price=float(p.price),
            category=p.category.name if p.category else "",
            relevance=getattr(p, 'relevance', 0.5),
        )
        for p in enriched
    ]
    return products, score_breakdown


def _rank_products(products, search_plan: dict, top_k: int = 10, skip_diversity: bool = False):
    """Weighted ranking: embedding (0.40) + price_fit (0.25) + rating (0.20) + sentiment (0.15).

    Args:
        products: list of Product model instances (with .relevance attribute set)
        search_plan: dict from SearchPlan.to_dict()
        top_k: max results to return
        skip_diversity: if True, skip diversity rerank (e.g. when brand_filter is set)

    Returns:
        (ranked_products, score_breakdown) where ranked_products are Product instances
        sorted by total score, and score_breakdown is a list of dicts with component scores.
    """
    if not products:
        return [], []

    budget_upper = search_plan.get("budget_upper")
    budget_lower = search_plan.get("budget_lower")

    ranked = []
    for p in products:
        embedding_score = float(getattr(p, 'faiss_similarity', getattr(p, 'relevance', 0.5)))

        price = float(getattr(p, 'price', 0) or 0)
        if budget_upper is not None and budget_lower is not None:
            mid = (budget_upper + budget_lower) / 2
            dist = abs(price - mid)
            price_fit = max(0.0, 1.0 - dist / max(mid, 0.01))
        else:
            price_fit = 1.0

        rating_raw = float(getattr(p, 'rating', 3.0) or 3.0)
        rating_norm = rating_raw / 5.0

        specs = getattr(p, 'specs', {}) or {}
        sentiment_raw = specs.get('review_sentiment', 0.7)
        if isinstance(sentiment_raw, str):
            sentiment_raw = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}.get(
                sentiment_raw.lower(), 0.5)
        sentiment = float(sentiment_raw)

        total = (
            0.40 * embedding_score +
            0.25 * price_fit +
            0.20 * rating_norm +
            0.15 * sentiment
        )

        p.relevance = total  # update relevance with final weighted score
        ranked.append((p, total, {
            "product_embedding": round(embedding_score, 3),
            "price_fit": round(price_fit, 3),
            "rating_norm": round(rating_norm, 3),
            "sentiment": round(sentiment, 3),
        }))

    ranked.sort(key=lambda x: x[1], reverse=True)

    # Diversity rerank: penalty for same-brand items after 2nd occurrence
    if not skip_diversity:
        brand_count: dict[str, int] = {}
        diverse = []
        for item in ranked:
            p, score, comp = item
            brand = getattr(p, 'brand', '') or ''
            brand_count[brand] = brand_count.get(brand, 0) + 1
            if brand_count[brand] <= 2:
                diverse.append(item)
            else:
                # Penalize 3rd+ same-brand item
                penalized_score = score * 0.85
                if penalized_score < diverse[-1][1]:
                    continue  # drop if penalized score falls below last diverse item
                diverse.append((p, penalized_score, comp))
        ranked = diverse

    top_ranked = ranked[:top_k]
    return (
        [r[0] for r in top_ranked],
        [{"product_id": r[0].id, "total": round(r[1], 3), "components": r[2]} for r in top_ranked],
    )


# ── Retrieval Mode ──────────────────────────────────────────────

def _resolve_mode(intent: str) -> str:
    """Resolve retrieval mode from intent.

    search    → semi-structured, brand filter or keyword → exact
    recommend → soft (embedding recall, diversity-favored ranking)
    explore   → soft + popular fallback
    """
    if intent == "search":
        return "soft"  # default to FAISS + ranking
    if intent == "recommend":
        return "soft"  # same retrieval, different ranking (more diversity)
    if intent == "explore":
        return "soft"  # popular fallback handled by response layer
