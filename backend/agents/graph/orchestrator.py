"""
Orchestrator — single entry point for the AI commerce system.

Pipeline:
  1. routing.classify(ctx)   → RouteDecision (may return terminal response)
  2. execution.run(ctx)      → AgentResult (status-based dispatch)
  3. response.build(ctx)     → final dict

All response paths pass through _enrich_response() — session_id, query_type
and runtime are injected at a single point, not scattered across stages.
"""

from __future__ import annotations

import logging
import time as _time

logger = logging.getLogger(__name__)

from .pipeline import PipelineContext
from .state import AgentState, ChatMessage
from .contracts.search_plan import normalize_query
from .routing import classify as stage_routing
from .execution import run as stage_execution
from .response import build as stage_response


def run(query: str, user_id: int | None = None,
        history: list[dict] | None = None,
        session_id: str = "",
        query_type: str = "",
        product_id: str = "",
        display_id: str = "") -> dict:
    """Run the full pipeline.  All paths exit through _enrich_response."""

    ctx = PipelineContext(
        query=query, user_id=user_id, session_id=session_id,
        query_type=query_type, product_id=product_id,
        display_id=display_id, history=history,
    )
    ctx._start = _time.time()
    ctx.state = _build_initial_state(ctx)

    result = _run_pipeline(ctx)
    return _enrich_response(result, ctx)


def _run_pipeline(ctx: PipelineContext) -> dict:
    """Internal: run the three-stage pipeline.  Returns a bare dict."""

    # Stage 1: Routing
    terminal = stage_routing(ctx)
    if terminal is not None:
        return terminal

    # Stage 2: Execution
    exec_result = stage_execution(ctx)
    if exec_result.status == "error":
        logger.error("Execution failed: %s", exec_result.response)
        return exec_result.response or {"reply": "系统内部错误，请稍后重试。"}
    if exec_result.status == "success" and exec_result.response is not None:
        # After purchase, remember for refund context
        _record_purchase_order(ctx.session_id, exec_result.response)
        return exec_result.response

    # Stage 3: Response
    return stage_response(ctx)


def _enrich_response(result: dict, ctx: PipelineContext) -> dict:
    """Inject pipeline-level metadata into every response.

    Uses setdefault so stages that already set these fields (e.g. affinity,
    response.build) are not overwritten.
    """
    result.setdefault("session_id", ctx.session_id)
    result.setdefault("query_type", ctx.query_type)
    if "runtime" not in result:
        result["runtime"] = {"total_ms": ctx.elapsed_ms()}
    return result


def _record_purchase_order(session_id: str, response: dict) -> None:
    """After a successful purchase, push order_id to recent_order_ids."""
    if not session_id:
        return
    # Purchase responses have agent_type="purchase" with an order_created_card block
    if response.get("agent_type") != "purchase":
        return
    blocks = response.get("blocks", [])
    for block in blocks:
        if block.get("type") == "order_created_card":
            order_id = block.get("data", {}).get("order_id")
            if order_id:
                from .session_memory import push_recent_order
                push_recent_order(session_id, str(order_id))
            break


# ═══════════════════════════════════════════════════════════════
# Initial state builder
# ═══════════════════════════════════════════════════════════════

def _build_initial_state(ctx: PipelineContext) -> AgentState:
    history_msgs = []
    if ctx.history:
        history_msgs = [
            ChatMessage(role=h.get("role", "user"), content=h.get("content", ""))
            for h in ctx.history[-10:]
        ]

    state = AgentState(
        user_query=ctx.query,
        user_id=ctx.user_id,
        session_id=ctx.session_id or "",
        history=history_msgs,
        normalized_query=normalize_query(ctx.query),
    )
    state.parallel_results["query_type"] = ctx.query_type

    if ctx.query_type in ("popular", "for-you", "trending", "similar"):
        state.parallel_results["recommend_type"] = ctx.query_type
    if ctx.product_id:
        state.parallel_results["similar_product_id"] = ctx.product_id
    if ctx.display_id:
        state.parallel_results["display_id"] = ctx.display_id

    return state
