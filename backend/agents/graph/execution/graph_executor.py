"""
Graph Executor — default fallback for search/recommend/explore/chat/analytics.

NOT registered in the dispatcher registry.  Called by execution/__init__.py
only when no domain executor claims the intent.

Runs the full LangGraph pipeline:
  ResponsePolicy → template / llm_direct / graph_full
  Graph path: memory hydration → constraint_parser → validator → graph.invoke()
"""

from __future__ import annotations

import logging

from ..pipeline import PipelineContext, AgentResult, UnrecoverableError
from ..state import AgentState, UserMemory, PurchaseSummary

logger = logging.getLogger(__name__)


def execute(ctx: PipelineContext) -> AgentResult:
    """Execute the classified intent via the appropriate path.

    Returns AgentResult with:
      status="success" → state has been updated, proceed to response stage
      status="fallback" → graph failed, unrecoverable
    """
    from ..response_policy import plan as policy_plan

    plan = policy_plan(ctx.final_route, ctx.commerce_result)

    # Resolved reference: always use graph (entry_router needs to dispatch it)
    from ..response_policy import ExecutionPlan, LLMPolicy
    if ctx.state.parallel_results.get("_resolved_ref") is not None:
        if plan.execution_mode in ("template", "llm_direct"):
            plan = ExecutionPlan(
                execution_mode="graph_full",
                memory="none",
                llm=LLMPolicy(max_tokens=2000, temperature=0.3, mode="graph_proxy"),
            )

    # Template path
    if plan.execution_mode == "template":
        return _execute_template(ctx)

    # ── LLM direct path ──
    if plan.execution_mode == "llm_direct":
        return _execute_llm_direct(ctx)

    # ── Graph path ──
    return _execute_graph(ctx, plan)


# ═══════════════════════════════════════════════════════════════
# Shared response helpers
# ═══════════════════════════════════════════════════════════════

def _base_response(ctx: PipelineContext, reply: str, intent: str,
                   confidence: float, message: str, blocks: list,
                   phase_label: str, expects_followup: bool = False) -> dict:
    """Build a terminal response dict shared by template and llm_direct paths."""
    result = {
        "reply": reply, "intent": intent,
        "confidence": confidence, "ui_state": "done",
        "message": message, "blocks": blocks,
        "ranked_items": [], "tool_results": {},
        "session_id": ctx.session_id, "query_type": ctx.query_type,
        "runtime": {
            "phases": [{"phase": "routing", "label": phase_label, "status": "ok", "ms": ctx.elapsed_ms()}],
            "total_ms": ctx.elapsed_ms(),
        },
        "explain": None, "retrieval": None,
        "show_budget_hint": False, "show_clarify_hint": False,
    }
    if ctx.session_id:
        from ..session_memory import put_conv_state
        from ..preprocessor import ConversationState
        cs = ctx.conv_state or ConversationState(session_id=ctx.session_id)
        cs.dialogue.last_user_query = ctx.query
        cs.dialogue.expects_followup = expects_followup
        put_conv_state(cs)
    return result


# ═══════════════════════════════════════════════════════════════
# Template path
# ═══════════════════════════════════════════════════════════════

def _execute_template(ctx: PipelineContext) -> AgentResult:
    from ..state_router import _pick_template

    reply = _pick_template(ctx.final_route.intent)
    return AgentResult(status="success", response=_base_response(
        ctx, reply, ctx.final_route.intent, ctx.final_route.confidence,
        ctx.final_route.reason, [], "快速路由", expects_followup=False,
    ))


# ═══════════════════════════════════════════════════════════════
# LLM direct path
# ═══════════════════════════════════════════════════════════════

def _execute_llm_direct(ctx: PipelineContext) -> AgentResult:
    from ..contracts.ui_state import AIResponse, UIState
    from ..nodes.chat_node import chat_node

    ctx.state.user_memory = None
    ctx.state = chat_node(ctx.state)

    ai_resp = AIResponse(
        ui_state=UIState.DONE,
        message=ctx.final_route.reason,
        confidence=ctx.final_route.confidence,
        blocks=[],
        reply=ctx.state.final_response,
        intent=ctx.final_route.intent,
    )
    return AgentResult(status="success", response=_base_response(
        ctx, ai_resp.reply, ai_resp.intent, ai_resp.confidence,
        ai_resp.message, [], "LLM直出", expects_followup=True,
    ))


# ═══════════════════════════════════════════════════════════════
# Graph path
# ═══════════════════════════════════════════════════════════════

def _execute_graph(ctx: PipelineContext, plan) -> AgentResult:
    # Memory hydration
    if ctx.user_id and plan.memory != "none":
        _hydrate_memory(ctx, plan)

    # Set preset_intent for entry_router (dispatch-only)
    if ctx.final_route.intent not in ("commerce", "unclear"):
        ctx.state.control_context["preset_intent"] = ctx.final_route.intent

    # ConstraintParser
    _parse_constraints(ctx)

    # Execution Validator
    _validate_plan(ctx)

    # Restore session memory (clarify context)
    from ..session_memory import get as get_session_memory
    session_mem = get_session_memory(ctx.session_id)
    if session_mem and session_mem.pending_intent:
        ctx.state.parallel_results["_clarify_answer"] = ctx.query
        ctx.state.parallel_results["_collected_slots"] = dict(session_mem.collected_slots)

    # Invoke graph
    from ..graph_builder import get_graph
    from ..fallback_graph import get_fallback_graph

    try:
        result = get_graph().invoke(ctx.state)
        ctx.state = AgentState(**result) if isinstance(result, dict) else result
    except Exception as e:
        try:
            ctx.state.error = str(e)
            result = get_fallback_graph().invoke(ctx.state)
            ctx.state = AgentState(**result) if isinstance(result, dict) else result
        except Exception as e2:
            raise UnrecoverableError(f"Both graphs failed: main={e}, fallback={e2}")

    return AgentResult(status="success")  # non-terminal; response stage builds final dict


# ═══════════════════════════════════════════════════════════════
# Graph-path helpers
# ═══════════════════════════════════════════════════════════════

def _hydrate_memory(ctx: PipelineContext, plan) -> None:
    from ..user_memory import load_preferences, load_purchase_profile, user_memory

    try:
        cache = getattr(ctx.state, '_memory_cache', None) or {}
        uid = ctx.user_id

        if plan.memory == "preferences":
            if "prefs" not in cache:
                cache["prefs"] = load_preferences(uid)
            ctx.state.user_memory = UserMemory(
                user_id=uid, preferences=cache["prefs"],
                purchase_summary=PurchaseSummary(),
            )
        elif plan.memory == "purchase":
            if "purchase" not in cache:
                cache["purchase"] = load_purchase_profile(uid)
            ctx.state.user_memory = UserMemory(
                user_id=uid, preferences={},
                purchase_summary=cache["purchase"],
            )
        else:  # full
            ctx.state.user_memory = user_memory.build(uid)

        ctx.state._memory_cache = cache
    except Exception:
        logger.warning("Memory hydration failed for user=%s", ctx.user_id, exc_info=True)


def _parse_constraints(ctx: PipelineContext) -> None:
    from ..nodes.constraint_parser import parse as parse_constraints
    from ..contracts.search_plan import QueryIntent

    plan = parse_constraints(ctx.query)
    ctx.state.parallel_results["_search_plan"] = plan.to_dict()
    ctx.state.parallel_results["_search_plan_raw"] = plan  # cached for _validate_plan
    if plan.is_structured():
        ctx.state.parallel_results["query_type"] = "search"
    elif plan.intent == QueryIntent.RECOMMEND:
        ctx.state.parallel_results["query_type"] = "recommend"
    phase = plan.to_phase()
    ctx.state.parallel_results["_search_phase_detail"] = phase.get("detail", "")
    ctx.state.parallel_results["_search_phase_label"] = phase.get("label", "")
    ctx.state.parallel_results["_show_budget_hint"] = plan.show_budget_hint
    ctx.state.parallel_results["_show_clarify_hint"] = plan.show_clarify_hint


def _validate_plan(ctx: PipelineContext) -> None:
    from ..execution_validator import validate as validate_plan, get_validated_recommend_type
    from ..decision_trace import DecisionTrace

    _has_history = bool(
        ctx.user_id and ctx.state.user_memory
        and ctx.state.user_memory.purchase_summary
        and ctx.state.user_memory.purchase_summary.total_orders > 0
    )
    _commerce_conf = ctx.commerce_result.confidence if ctx.commerce_result else 0.0
    _current_rec_type = ctx.state.parallel_results.get("recommend_type", "")

    # Reuse plan from _parse_constraints (avoid double parse)
    plan = ctx.state.parallel_results.get("_search_plan_raw")
    if plan is None:
        # Safety fallback — should not happen in normal pipeline
        from ..nodes.constraint_parser import parse as parse_constraints
        plan = parse_constraints(ctx.query)

    validated = validate_plan(
        plan=plan, query=ctx.query, commerce_confidence=_commerce_conf,
        recommend_type=_current_rec_type, intent=ctx.final_route.intent,
        user_id=ctx.user_id, has_history=_has_history,
    )

    ctx.state.parallel_results["_search_plan"] = validated.to_dict()
    if validated.downgraded and ctx.state.parallel_results.get("query_type") == "search":
        ctx.state.parallel_results["query_type"] = "recommend"

    corrected_rec_type = get_validated_recommend_type(validated)
    ctx.state.parallel_results["recommend_type"] = corrected_rec_type
    ctx.state.parallel_results["_validator_decisions"] = validated.to_dict()

    _dt = DecisionTrace(
        session_id=ctx.session_id, query=ctx.query, plan_version="v2",
        plan_raw=plan.to_dict(), plan_validated=validated.to_dict(),
        validation_decisions=[d.to_dict() for d in validated.decisions],
        plan_downgraded=validated.downgraded,
    )
    ctx.state.parallel_results["_decision_trace"] = _dt
