"""
entry_router node — LangGraph dispatcher with ResolvedReference dispatch.

Dispatch priority:
  0. ResolvedReference — read _resolved_ref from parallel_results, clarify or
     direct-dispatch via ACTION_TO_CAPABILITY (PURCHASE→order, ADD_TO_CART→cart,
     VIEW_DETAIL→search)
  1. Preset intent from state_router
  2. ConstraintParser override (search_plan intent)
  3. Session memory (follow-up answer to clarify question)
  4. Default → "chat"

PR4: Path 0 upgraded from _try_resolve_reference to ResolvedReference.
"""

import logging

from langgraph.types import Command

from ..state import AgentState

logger = logging.getLogger(__name__)

_CONSTRAINT_NODE_MAP: dict[str, str] = {"sort": "search", "recommend": "recommend"}
VALID_INTENTS = {"search", "recommend", "order", "analytics", "chat"}


def entry_router(state: AgentState) -> Command:
    """Dispatch to the correct graph node.  Reference resolution runs first."""

    query = state.user_query or ""
    session_id = state.session_id or ""

    # ═══════════════════════════════════════════════════════════
    # Path 0: ResolvedReference dispatch (runs BEFORE all other paths)
    # ═══════════════════════════════════════════════════════════
    resolved_ref = state.parallel_results.get("_resolved_ref")
    if resolved_ref is not None:
        from agents.graph.routing.reference_resolver import (
            ResolvedReference, ReferenceAction, ClarificationReason,
        )

        # Clarification needed
        if resolved_ref.requires_clarification:
            reason = resolved_ref.clarification_reason
            if reason == ClarificationReason.ACTION_MISSING:
                msg = f"已找到「{resolved_ref.product_name}」，你想：\n1. 查看详情\n2. 加入购物车\n3. 立即购买"
            elif reason == ClarificationReason.PRODUCT_NOT_FOUND:
                msg = f"上次只展示了 {resolved_ref.source_index} 个以内的商品，请重新选择。"
            else:
                msg = "你想查看详情、加购物车还是购买？"
            return Command(goto="chat", update={
                "intent": "chat",
                "confidence": 0.9,
                "routing_method": "reference_clarify",
                "current_node": "entry_router",
                "ui_message": msg,
                "parallel_results": {
                    **state.parallel_results,
                    "_clarify_reference": True,
                },
            })

        # Direct action dispatch
        if resolved_ref.action is not None:
            if resolved_ref.action == ReferenceAction.PURCHASE:
                return _dispatch_purchase(state, resolved_ref)
            if resolved_ref.action == ReferenceAction.ADD_TO_CART:
                return _dispatch_cart(state, resolved_ref)
            if resolved_ref.action == ReferenceAction.VIEW_DETAIL:
                return Command(goto="search", update={
                    "intent": "search",
                    "confidence": 0.95,
                    "routing_method": "reference_action",
                    "current_node": "entry_router",
                    "ui_message": f"查看「{resolved_ref.product_name}」详情",
                    "parallel_results": state.parallel_results,
                })

    # Base update — always include parallel_results so LangGraph
    # preserves any in-place mutations.
    base_update = {
        "current_node": "entry_router",
        "parallel_results": state.parallel_results,
    }

    # ── Path 1: Preset intent ──
    preset = state.control_context.get("preset_intent", "")
    if preset in VALID_INTENTS:
        return Command(goto=preset, update={
            **base_update,
            "intent": preset, "confidence": 0.9,
            "routing_method": "preset",
            "ui_message": f"匹配到「{preset}」意图（路由预设）",
        })

    # ── Path 2: ConstraintParser ──
    search_plan = state.parallel_results.get("_search_plan")
    if search_plan:
        intent = search_plan.get("intent", "chat")
        if intent != "ambiguous":
            goto = _CONSTRAINT_NODE_MAP.get(intent, intent)
            if goto not in VALID_INTENTS:
                goto = "chat"
            return Command(goto=goto, update={
                **base_update,
                "intent": goto, "confidence": 0.95,
                "routing_method": "constraint_parser",
                "ui_message": f"匹配到「{intent}」意图（约束解析）",
            })

    # ── Path 3: Session memory ──
    from agents.graph.session_memory import get as get_session_memory, collect_answer
    session_mem = get_session_memory(session_id)
    if session_mem and session_mem.pending_intent:
        if session_mem.missing_slots:
            for slot_key in session_mem.missing_slots:
                collect_answer(session_id, slot_key, query)
        return Command(goto=session_mem.pending_intent, update={
            **base_update,
            "intent": session_mem.pending_intent, "confidence": 1.0,
            "routing_method": "session", "clarify_round": 1,
            "ui_message": f"继续「{session_mem.pending_intent}」流程…",
        })

    # ── Path 4: Default ──
    logger.info("No preset_intent — defaulting to chat")
    return Command(goto="chat", update={
        **base_update,
        "intent": "chat", "confidence": 0.5,
        "routing_method": "default",
        "ui_message": "你好！有什么可以帮你的？",
    })


# ═══════════════════════════════════════════════════════════════
# Reference dispatch helpers — call domain agents directly
# ═══════════════════════════════════════════════════════════════


def _dispatch_purchase(state: AgentState, ref) -> Command:
    """Call PurchaseAgent directly with resolved reference, bypass graph."""
    import django; django.setup()
    from agents.purchase.agent import _run as purchase_run

    result = purchase_run(
        query=state.user_query or "",
        user_id=state.user_id,
        session_id=state.session_id or "",
        resolved_ref=ref,
    )
    return Command(goto="chat", update={
        "intent": "purchase",
        "confidence": 0.95,
        "routing_method": "reference_action",
        "current_node": "entry_router",
        "ui_message": result.get("reply", result.get("message", "")),
        "final_response": result.get("reply", ""),
        "tool_results": {"purchase": result},
        "parallel_results": state.parallel_results,
    })


def _dispatch_cart(state: AgentState, ref) -> Command:
    """Call CartAgent directly with resolved reference, bypass graph."""
    import django; django.setup()
    from agents.cart.agent import CartAgent
    from agents.graph.pipeline import AgentContext, AgentResult

    agent = CartAgent()
    agent_ctx = AgentContext(
        query=f"add {ref.product_id}",
        user_id=state.user_id,
        session_id=state.session_id or "",
    )
    result: AgentResult = agent.execute(agent_ctx)
    if result.status == "success" and result.response:
        reply = result.response.get("reply", "已加入购物车")
    else:
        reply = "加入购物车失败，请重试"
    return Command(goto="chat", update={
        "intent": "cart",
        "confidence": 0.95,
        "routing_method": "reference_action",
        "current_node": "entry_router",
        "ui_message": reply,
        "final_response": reply,
        "parallel_results": state.parallel_results,
    })


