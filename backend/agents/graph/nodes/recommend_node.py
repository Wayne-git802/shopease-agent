"""
Recommend Node — wraps the legacy RecommendEngine.

I/O Contract:
  Input:  RecommendNodeInput  (products, user_id, user_memory)
  Output: RecommendNodeOutput (ranked_items, score_distribution)
  side_effect: delegates ranking to RecommendEngine; no LLM calls.
"""
import time

from ..state import AgentState, RankedItem, NodeTrace
from ..contracts import RecommendNodeInput, RecommendNodeOutput
from ..session_memory import get as get_session_memory
from ..contracts.product_domain import SLOT_BY_KEY, REQUIRED_SLOTS, MAX_CLARIFY_ROUNDS
from agents.recommend.engine import RecommendEngine


# ═══════════════════════════════════════════════════════════════
# State Reconciliation & Category Filter
# ═══════════════════════════════════════════════════════════════

def _hydrate_slots_from_resolved_params(state: AgentState, collected_slots: dict) -> dict:
    """
    State reconciliation layer — not recommend business logic.

    Preprocessor resolves slots (budget, brand, etc.) and stores them in
    _resolved_params. But session_memory.collected_slots is the canonical
    slot store consumed by the rest of recommend_node. This function
    bridges the gap: reads _resolved_params, writes to collected_slots.

    Rule: this is the ONLY place where _resolved_params → collected_slots
    translation happens. Future slots go here.
    """
    resolved = state.parallel_results.get("_resolved_params", {})
    if not resolved:
        return collected_slots

    slots = dict(collected_slots)

    # budget: _slot_value ("0 - 6") → collected_slots["budget"]
    if not slots.get("budget") and resolved.get("_slot_value"):
        slots["budget"] = resolved["_slot_value"]
        try:
            from ..contracts.budget_tiers import get_budget_range
            lo, hi = get_budget_range(resolved["_slot_value"])
            state.parallel_results["budget_lo"] = lo
            state.parallel_results["budget_hi"] = hi
        except Exception:
            pass  # graceful degradation

    return slots


def _apply_category_filter(engine_results: list[dict], plan_dict: dict) -> list[dict]:
    """
    Safe DB-level category filter.

    ConstraintParser owns category semantics (keywords → slugs).
    This function is a pure consumer: applies the already-normalized
    category_filter as a safe substring match. Does NOT interpret,
    translate, or modify the filter value.

    Graceful degradation: empty result → return original, don't drop all.
    """
    category_filter = plan_dict.get("category_filter")
    if not category_filter or not engine_results:
        return engine_results

    filtered = [
        item for item in engine_results
        if category_filter in (item.get("category", "") or "").lower()
    ]
    return filtered if filtered else engine_results


# ═══════════════════════════════════════════════════════════════
# Reason generation helpers
# ═══════════════════════════════════════════════════════════════

def generate_query_reasons(item: RankedItem, engine_item: dict, state: AgentState, collected_slots: dict) -> list[str]:
    reasons = []
    if collected_slots.get("budget"):
        reasons.append(f"预算: {collected_slots['budget']}")
    return reasons


def generate_memory_reasons(item: RankedItem, engine_item: dict, state: AgentState) -> list[str]:
    reasons = []
    if state.user_memory and state.user_memory.preferences:
        top = sorted(state.user_memory.preferences.items(), key=lambda x: x[1], reverse=True)[:3]
        cat = engine_item.get("category_name", "") if isinstance(engine_item, dict) else ""
        for pref_cat, score in top:
            if score > 0.15 and pref_cat in cat:
                reasons.append(f"偏好: {pref_cat}")
    return reasons


def generate_ranking_reasons(item: RankedItem, engine_item: dict, all_results: list[dict]) -> list[str]:
    reasons = []
    score = engine_item.get("score", 0) if isinstance(engine_item, dict) else item.score
    rating = engine_item.get("rating", 0) if isinstance(engine_item, dict) else 0
    if isinstance(rating, (int, float)) and rating >= 4.5:
        reasons.append("高评分")
    if isinstance(rating, (int, float)) and 4.0 <= rating < 4.5:
        reasons.append("性价比高")
    idx = all_results.index(engine_item) if isinstance(engine_item, dict) and all_results else -1
    if 0 <= idx < 3:
        reasons.append("最佳匹配")
    return reasons


def recommend_node(state: AgentState) -> AgentState:
    """Wrap legacy RecommendEngine to produce ranked_items."""

    start = time.time()

    # --- Load session memory for slot enrichment ---
    session_mem = get_session_memory(state.session_id)
    collected_slots = session_mem.collected_slots if session_mem else {}

    # State reconciliation: preprocessor's resolved slots → collected_slots
    collected_slots = _hydrate_slots_from_resolved_params(state, collected_slots)

    # ── P3: Check for missing required fields ──
    if state.clarify_round < MAX_CLARIFY_ROUNDS:
        missing = []
        for slot_def in REQUIRED_SLOTS:
            if slot_def.key not in collected_slots:
                if state.user_memory and state.user_memory.preferences:
                    strong_prefs = {k: v for k, v in state.user_memory.preferences.items() if v > 0.1}
                    if len(strong_prefs) >= 3:
                        continue
                missing.append(slot_def.key)
        state.missing_fields = missing

    # ── P3: Apply collected slots as filters ──
    if "budget" in collected_slots:
        budget_str = collected_slots["budget"]
        try:
            from ..contracts.budget_tiers import get_budget_range
            lo, hi = get_budget_range(budget_str)
            state.parallel_results["budget_lo"] = lo
            state.parallel_results["budget_hi"] = hi
        except Exception:
            pass

    engine = RecommendEngine()

    # ── Phase B-1: Inject feedback-modulated weights ───────────
    from ..feedback.weight_injector import modulate_batch
    from ..feedback.signal_store import signal_count

    # ── Determine which recommendation strategy to use ────────────
    recommend_type = state.parallel_results.get("recommend_type", "")

    if not recommend_type:
        # Default: intent-based routing
        if state.intent == "recommend":
            recommend_type = "for-you"
        else:
            recommend_type = "popular"

    # ── Call the appropriate engine method ────────────────────────
    engine_results: list[dict] = []

    if recommend_type == "for-you":
        user_id = state.user_id if state.user_id is not None else 0
        engine_results = engine.get_for_user(user_id)

    elif recommend_type == "similar":
        product_id = state.parallel_results.get("similar_product_id", 0)
        engine_results = engine.get_similar(int(product_id))

    elif recommend_type == "trending":
        engine_results = engine.get_trending()

    elif recommend_type == "popular":
        engine_results = engine.get_popular()

    else:
        # Unknown type: fall back to popular
        engine_results = engine.get_popular()

    # Category filter: apply SearchPlan.category_filter to engine results
    engine_results = _apply_category_filter(
        engine_results, state.parallel_results.get("_search_plan", {}))

    # Budget price filter: apply budget_lo / budget_hi to engine results
    budget_lo = state.parallel_results.get("budget_lo")
    budget_hi = state.parallel_results.get("budget_hi")
    if budget_lo is not None and budget_hi is not None and engine_results:
        filtered = []
        for item in engine_results:
            try:
                price = float(item.get("price", 0))
                if budget_lo <= price <= budget_hi:
                    filtered.append(item)
            except (ValueError, TypeError):
                filtered.append(item)  # keep if price unparseable
        if filtered:
            engine_results = filtered

    # ── Phase B-1: Inject feedback signals into scores ───────────
    if engine_results and state.user_id:
        n_signals = signal_count(state.user_id)
        if n_signals > 0:
            engine_results = modulate_batch(engine_results, state.user_id)
            state.parallel_results["_feedback_signals_applied"] = n_signals
            boosted_cats = set()
            for item in engine_results:
                if item.get("_signal_boost", 0) != 0:
                    boosted_cats.add(item.get("category_name", ""))
            state.parallel_results["_feedback_categories"] = list(boosted_cats)[:5]

    # ── Build relevance lookup from retrieved_products ────────────
    relevance_map: dict[int, float] = {
        p.id: p.relevance for p in state.retrieved_products
    }

    # ── Convert engine dicts → RankedItem list ────────────────────
    ranked: list[RankedItem] = []
    for item in engine_results:
        product_id = item.get("product_id", 0)
        # Use stored relevance if available, else default to 1.0
        score = relevance_map.get(product_id, 1.0)
        ranked.append(RankedItem(
            id=product_id,
            score=score,
            source="recommend",
        ))

    # ── P3: Generate reasons for each RankedItem ──
    for ritem in ranked:
        # Find matching engine result dict
        matching_engine_item = next(
            (ei for ei in engine_results if ei.get("product_id") == ritem.id),
            {},
        )
        ritem.reasons.extend(
            generate_query_reasons(ritem, matching_engine_item, state, collected_slots)
        )
        ritem.reasons.extend(
            generate_memory_reasons(ritem, matching_engine_item, state)
        )
        ritem.reasons.extend(
            generate_ranking_reasons(ritem, matching_engine_item, engine_results)
        )

    # ── Store raw product dicts for frontend card rendering ────────
    state.tool_results["products"] = engine_results

    # ── Populate state ────────────────────────────────────────────
    latency = int((time.time() - start) * 1000)

    state.ranked_items = ranked
    state.score_distribution["recommend_mean"] = (
        sum(r.score for r in ranked) / max(len(ranked), 1)
    )
    state.current_node = "recommend"
    n = len(state.ranked_items)
    base_msg = f"为你找到 {n} 款商品" if n else "正在检索你的偏好…"
    sig_count = state.parallel_results.get("_feedback_signals_applied", 0)
    if sig_count:
        cats = state.parallel_results.get("_feedback_categories", [])
        cat_str = "、".join(cats[:3]) if cats else "你的偏好"
        state.ui_message = f"{base_msg}，已注入 {sig_count} 条反馈信号（{cat_str}）"
    else:
        state.ui_message = base_msg if n else "正在检索你的偏好…"
    state.steps_done.append("recommend")

    state.trace.append(NodeTrace(
        node_name="recommend",
        model_name="",
        latency_ms=latency,
    ))

    return state
