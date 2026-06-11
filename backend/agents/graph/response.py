"""
Response Builder — trace, blocks, AIResponse, SessionTrace persistence.

Builds the final API response dict from executed AgentState.
Called after execution stage completes successfully.

All logic extracted from orchestrator.run() sections 7–8.  No new logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .pipeline import PipelineContext
from .contracts.ui_state import AIResponse, UIState, UIBlock, NODE_TO_UI_STATE, UI_STATE_MESSAGES
from .trace import (
    persist_trace, RuntimeTrace, PhaseRecord, NODE_TO_PHASE, PHASE_LABELS,
)

logger = logging.getLogger(__name__)

# ── Capability-bound safety ─────────────────────────────────────

BANNED_PHRASES = [
    "已为您转接", "人工客服", "稍后联系您", "已经通知商家", "已通知商家",
    "仓库正在", "优惠券已发放", "退款已到账", "已帮您退款",
    "退款成功", "已经退款", "已取消订单", "已为您取消",
    "已发货", "正在打包", "物流已更新",
]

_SANITIZE_REPLACEMENT = (
    "如需人工帮助，请查看商品页面的商家联系方式。"
    "退款或取消订单需要通过订单页面操作，我会引导你完成确认流程。"
)


# ═══════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════

def build(ctx: PipelineContext) -> dict:
    """Build the final response dict. Always returns a terminal dict."""
    state = ctx.state

    # 1. Safety check
    state.final_response = _sanitize(state.final_response or "")

    # 2. Persist trace
    _persist_trace(state)

    # 3. Update long-term memory
    _update_memory(ctx.user_id, state)

    # 4. Session memory lifecycle
    _manage_session(ctx, state)

    # 5. Clarify answer persistence
    _persist_clarify(ctx, state)

    # 6. Build UI components
    runtime_dict = _build_runtime(state)
    explain_dict = _build_explain(state)
    retrieval_dict = _build_retrieval(state)
    blocks = _build_blocks(ctx, state)

    # 7. AIResponse
    clarify_data = state.tool_results.get("_clarify")
    last_node = state.current_node or (state.steps_done[-1] if state.steps_done else "chat")
    ui_state = UIState.CLARIFYING if clarify_data else NODE_TO_UI_STATE.get(last_node, UIState.DONE)
    message = state.ui_message or UI_STATE_MESSAGES.get(ui_state, "")

    trace_summary = None
    if state.trace:
        last_trace = state.trace[-1]
        trace_summary = {
            "total_ms": sum(t.latency_ms for t in state.trace),
            "last_node": last_trace.node_name,
            "model": last_trace.model_name or "fast",
            "cache_hit": last_trace.cache_hit,
        }

    response = AIResponse(
        ui_state=ui_state, message=message, confidence=state.confidence,
        blocks=blocks, reply=state.final_response, intent=state.intent,
        trace=trace_summary,
        show_budget_hint=state.parallel_results.get("_show_budget_hint", False),
        show_clarify_hint=state.parallel_results.get("_show_clarify_hint", False),
    )

    result = response.model_dump()
    result["runtime"] = runtime_dict
    result["explain"] = explain_dict
    result["retrieval"] = retrieval_dict

    # 8. Persist SessionTrace
    _persist_session_trace(ctx, state, blocks, runtime_dict)

    return result


# ═══════════════════════════════════════════════════════════════
# Safety
# ═══════════════════════════════════════════════════════════════

def _sanitize(text: str) -> str:
    if not text:
        return text
    for phrase in BANNED_PHRASES:
        if phrase in text:
            logger.warning("Banned phrase detected: '%s' — sanitizing response", phrase)
            return _SANITIZE_REPLACEMENT
    return text


# ═══════════════════════════════════════════════════════════════
# Trace + Memory
# ═══════════════════════════════════════════════════════════════

def _persist_trace(state) -> None:
    try:
        persist_trace(state.trace)
    except Exception:
        logger.warning("Trace persist failed for session=%s", state.session_id, exc_info=True)


def _update_memory(user_id, state) -> None:
    if not user_id:
        return
    try:
        from .memory_manager import memory_manager
        memory_manager.update(state)
    except Exception:
        logger.warning("Memory update failed for user=%s", user_id, exc_info=True)


# ═══════════════════════════════════════════════════════════════
# Session lifecycle
# ═══════════════════════════════════════════════════════════════

def _manage_session(ctx: PipelineContext, state) -> None:
    from .session_memory import (
        put as put_session_memory, clear as clear_session_memory,
        put_conv_state, SessionMemory,
    )
    from .preprocessor import build_conversation_state

    clarify_data = state.tool_results.get("_clarify")
    session_id = ctx.session_id
    has_cards = bool(state.tool_results.get("products"))
    is_clarify_ref = state.parallel_results.get("_clarify_reference", False)

    if clarify_data and session_id:
        sm = SessionMemory(
            session_id=session_id,
            pending_intent=state.intent,
            collected_slots=state.parallel_results.get("_collected_slots", {}),
            missing_slots=state.missing_fields,
        )
        put_session_memory(sm)
        cs = build_conversation_state(
            session_id=session_id, last_intent=state.intent,
            original_query=ctx.query, clarify_data=clarify_data,
            ai_reply=state.final_response,
        )
        cs.dialogue.last_user_query = ctx.query
        cs.dialogue.expects_followup = has_cards or is_clarify_ref
        if is_clarify_ref:
            ref = state.parallel_results.get("_resolved_ref")
            if ref and hasattr(ref, 'target') and ref.target.product_ids:
                from .preprocessor import PendingReference
                cs.pending_reference = PendingReference(
                    product_id=ref.target.product_ids[0],
                    product_name=ref.product_name,
                    waiting_for=ref.clarification_reason,
                )
        put_conv_state(cs)
    elif session_id:
        clear_session_memory(session_id)
        cs = build_conversation_state(
            session_id=session_id, last_intent=state.intent,
            original_query=ctx.query, clarify_data=None,
            ai_reply=state.final_response,
        )
        cs.dialogue.last_user_query = ctx.query
        cs.dialogue.expects_followup = has_cards or is_clarify_ref
        if is_clarify_ref:
            ref = state.parallel_results.get("_resolved_ref")
            if ref and hasattr(ref, 'target') and ref.target.product_ids:
                from .preprocessor import PendingReference
                cs.pending_reference = PendingReference(
                    product_id=ref.target.product_ids[0],
                    product_name=ref.product_name,
                    waiting_for=ref.clarification_reason,
                )
        put_conv_state(cs)


def _persist_clarify(ctx: PipelineContext, state) -> None:
    from .session_memory import get as get_session_memory

    clarify_data = state.tool_results.get("_clarify")
    session_mem = get_session_memory(ctx.session_id)

    if ctx.user_id and session_mem and session_mem.pending_intent and not clarify_data:
        collected = state.parallel_results.get("_collected_slots", {})
        if collected:
            try:
                from .feedback.memory_distribution import merge_preference
                for slot_key, slot_value in collected.items():
                    merge_preference(
                        key=slot_key, new_value=str(slot_value),
                        user_id=ctx.user_id, source="clarify",
                    )
            except Exception:
                logger.warning("Clarify preference merge failed for user=%s", ctx.user_id, exc_info=True)


# ═══════════════════════════════════════════════════════════════
# Runtime / Explain / Retrieval
# ═══════════════════════════════════════════════════════════════

def _build_runtime(state) -> dict | None:
    rt = RuntimeTrace()
    if state.trace:
        for t in state.trace:
            phase = NODE_TO_PHASE.get(t.node_name, "responding")
            label = PHASE_LABELS.get(phase, phase)
            detail = ""
            if t.node_name == "search":
                plan_label = state.parallel_results.get("_search_phase_label", "")
                plan_detail = state.parallel_results.get("_search_phase_detail", "")
                if plan_label:
                    label = plan_label
                if plan_detail:
                    detail = plan_detail
            rt.phases.append(PhaseRecord(
                phase=phase, label=label, status="ok", ms=t.latency_ms, detail=detail,
            ))
        rt.total_ms = sum(t.latency_ms for t in state.trace)
    return rt.to_dict() if rt.phases else None


def _build_explain(state) -> dict | None:
    if not state.ranked_items:
        return None
    factors = []
    seen = set()
    for item in state.ranked_items[:5]:
        for reason in (item.reasons or [])[:2]:
            if reason not in seen:
                seen.add(reason)
                factors.append({"label": reason})
                if len(factors) >= 4:
                    break
        if len(factors) >= 4:
            break
    if factors:
        return {"title": "为什么推荐这些？", "factors": factors}
    return None


def _build_retrieval(state) -> dict | None:
    search_meta = state.tool_results.get("_search_meta")
    if not search_meta:
        return None
    return {
        "summary": "基于商品描述、评论和相似商品分析",
        "detail": (
            f"{search_meta.get('candidates', 0)} 候选 → "
            f"{search_meta.get('after_filter', 0)} 过滤 → "
            f"{search_meta.get('after_rank', 0)} 排序"
        ),
    }


# ═══════════════════════════════════════════════════════════════
# UI Blocks
# ═══════════════════════════════════════════════════════════════

def _build_blocks(ctx: PipelineContext, state) -> list[UIBlock]:
    blocks: list[UIBlock] = []
    clarify_data = state.tool_results.get("_clarify")
    products = state.tool_results.get("products")

    # Clarify block
    if clarify_data:
        blocks.append(UIBlock(type="clarify", data={
            "slot_key": clarify_data.get("slot_key", ""),
            "question": clarify_data.get("question", ""),
            "options": clarify_data.get("options", []),
        }))

    # Explain block
    if state.ranked_items:
        explained_items = []
        for item in state.ranked_items[:5]:
            if item.reasons:
                name = str(item.id)
                for p in (products or []):
                    if p.get("product_id") == item.id or p.get("id") == item.id:
                        name = p.get("name", str(item.id))
                        break
                explained_items.append({"name": name, "reasons": item.reasons})
        if explained_items:
            blocks.append(UIBlock(type="explain", data={
                "summary": f"为什么推荐这 {len(explained_items)} 款商品？",
                "items": explained_items,
            }))

    # Product cards
    if state.intent in ("recommend", "search") and products:
        import uuid as _uuid
        did = f"disp_{_uuid.uuid4().hex[:12]}"
        try:
            from .display_context import put_display
            put_display(did, state.intent, products)
        except Exception:
            logger.warning("Display context write failed for intent=%s", state.intent, exc_info=True)
        blocks.append(UIBlock(type="product_card", data={
            "products": products, "display_id": did,
        }))
    elif state.intent in ("recommend", "search"):
        blocks.append(UIBlock(type="message", data={
            "text": "没有找到完全匹配的商品，以下是为您推荐的热门商品：", "level": "info",
        }))
        try:
            from agents.commerce.engine import RecommendEngine
            popular = RecommendEngine().get_popular()
            if popular:
                blocks.append(UIBlock(type="product_card", data={"products": popular}))
        except Exception:
            logger.warning("Popular fallback failed for session=%s", ctx.session_id, exc_info=True)
    elif state.intent == "analytics":
        blocks.append(UIBlock(type="report", data={"markdown": state.final_response}))
    elif state.tool_results.get("health"):
        h = state.tool_results["health"]
        blocks.append(UIBlock(type="metric", data={"status": h.get("status", "unknown")}))

    return blocks


# ═══════════════════════════════════════════════════════════════
# SessionTrace persistence
# ═══════════════════════════════════════════════════════════════

def _persist_session_trace(ctx: PipelineContext, state, blocks, runtime_dict) -> None:
    try:
        from agents.models import SessionTrace
        from .decision_trace import DecisionTrace, BranchDecision, snapshot_signals

        # Build ranked snapshots
        before = [
            {"id": p.id, "name": p.name, "price": p.price, "category": p.category}
            for p in (state.retrieved_products or [])[:10]
        ]
        after = [
            {"id": r.id, "name": "", "price": 0, "category": ""}
            for r in (state.ranked_items or [])[:10]
        ]
        products_raw = state.tool_results.get("products", [])
        prod_map = {p.get("product_id", 0): p for p in products_raw if isinstance(p, dict)}
        for i, r in enumerate((state.ranked_items or [])[:10]):
            pdata = prod_map.get(r.id, {})
            after[i] = {
                "id": r.id,
                "name": pdata.get("product_name", pdata.get("name", "")),
                "price": float(pdata.get("price", 0)),
                "category": pdata.get("category_name", ""),
            }

        # Signals
        signals = {}
        cats = state.parallel_results.get("_feedback_categories", [])
        if cats and state.user_id:
            from .feedback.signal_store import get_user_signals
            all_sigs = get_user_signals(state.user_id)
            signals = {cat: round(all_sigs.get(cat, 0), 3) for cat in cats if cat in all_sigs}

        # Events
        events = _build_events(state, signals)

        # DecisionTrace enrichment
        _dt = state.parallel_results.get("_decision_trace")
        _dt_dict = {}
        if isinstance(_dt, DecisionTrace):
            _enrich_decision_trace(state, _dt)
            _dt.signal_snapshot = snapshot_signals(state.user_id)
            _dt.recorded_at = datetime.now(timezone.utc).isoformat()
            _dt_dict = _dt.to_dict()

        SessionTrace.objects.update_or_create(
            session_id=ctx.session_id,
            defaults={
                "user_id": state.user_id,
                "query": ctx.query,
                "intent": state.intent,
                "routing_conf": state.confidence,
                "ui_state": (
                    UIState.CLARIFYING.value
                    if state.tool_results.get("_clarify")
                    else NODE_TO_UI_STATE.get(
                        state.current_node or (state.steps_done[-1] if state.steps_done else "chat"),
                        UIState.DONE,
                    ).value
                ),
                "reply": (state.final_response or "")[:500],
                "phases": runtime_dict["phases"] if runtime_dict else [],
                "events": events,
                "ranked_before": before,
                "ranked_after": after,
                "signals_applied": signals,
                "block_count": len(blocks),
                "total_ms": runtime_dict["total_ms"] if runtime_dict else 0,
                "decision_trace": _dt_dict,
            },
        )
    except Exception as e:
        logger.warning(
            "SessionTrace write failed for session=%s: %s", ctx.session_id, e, exc_info=True,
        )


def _build_events(state, signals) -> list[dict]:
    def _node_ms(name: str) -> int:
        for t in (state.trace or []):
            if t.node_name == name:
                return t.latency_ms
        return 0

    search_meta = state.tool_results.get("_search_meta", {})
    search_plan = state.parallel_results.get("_search_plan", {})

    events = [
        {
            "block": "routing", "type": "classify",
            "ms": _node_ms("entry_router"),
            "payload": {
                "intent": state.intent,
                "confidence": round(state.confidence, 3),
                "method": state.routing_method,
            },
        },
        {
            "block": "retrieval",
            "type": search_plan.get("strategy", "semantic"),
            "ms": _node_ms("search") or _node_ms("recommend"),
            "payload": {
                "strategy": search_plan.get("strategy", "semantic"),
                "sort_by": search_plan.get("sort_by"),
                "direction": search_plan.get("direction"),
                "candidates": search_meta.get("candidates", 0),
                "after_filter": search_meta.get("after_filter", 0),
                "after_rank": search_meta.get("after_rank", 0),
            },
        },
        {
            "block": "ranking", "type": "rerank",
            "ms": _node_ms("merge"),
            "payload": {
                "before_count": len(state.retrieved_products or []),
                "after_count": len(state.ranked_items or []),
                "changes": _ranking_changes(state),
                "signals": [f"{k} {v:+.2f}" for k, v in signals.items()] if signals else [],
            },
        },
        {
            "block": "response", "type": "generate",
            "ms": _node_ms("generate") or _node_ms("chat"),
            "payload": {
                "length": len(state.final_response or ""),
                "has_reply": bool(state.final_response),
            },
        },
    ]
    return events


def _ranking_changes(state) -> list[dict]:
    changes = []
    if state.ranked_items:
        before_ids = [p.id for p in (state.retrieved_products or [])[:10]]
        for i, r in enumerate(state.ranked_items[:10]):
            if r.id in before_ids:
                old_idx = before_ids.index(r.id)
                delta = old_idx - i
                if delta != 0:
                    changes.append({
                        "product_id": r.id, "before": old_idx + 1,
                        "after": i + 1, "delta": delta,
                    })
    return changes


def _enrich_decision_trace(state, dt) -> None:
    from .decision_trace import BranchDecision

    strategy_dec = state.parallel_results.get("_search_strategy_decision", {})
    struct_count = len(state.parallel_results.get("_structured_products", []))
    merged = state.parallel_results.get("_merge_policy", {})

    dt.node_decisions = [
        BranchDecision(
            node="search",
            branch=strategy_dec.get("strategy", "semantic"),
            reason=strategy_dec.get("reason", ""),
            inputs={
                "strategy": strategy_dec.get("strategy", "semantic"),
                "dual_source": strategy_dec.get("dual_source", False),
                "structured_count": struct_count,
                "semantic_count": len(state.retrieved_products or []),
            },
        ),
        BranchDecision(
            node="recommend",
            branch=state.parallel_results.get("recommend_type", "popular"),
            reason=f"intent={state.intent}, user_id={state.user_id}",
            inputs={"intent": state.intent},
        ),
        BranchDecision(
            node="merge",
            branch="fusion_p1",
            reason=(
                f"policy={merged.get('policy', 'default')}, "
                f"sw={merged.get('search_weight', 0.5)}, "
                f"rw={merged.get('rec_weight', 0.5)}, "
                f"div={merged.get('diversity_lambda', 0.25)}"
            ),
            inputs={
                "search_count": len(state.retrieved_products or []),
                "rec_count": len(state.ranked_items or []),
                "struct_count": struct_count,
                "policy": merged,
            },
        ),
    ]
