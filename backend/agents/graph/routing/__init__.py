"""
Routing — intent classification, unified constraint parsing, and grounding.

Pipeline:
  affinity.check()        → fast-path routing
  classifier.classify()   → L0+L1+signal fusion
  search_plan_builder     → unified constraint + strategy + state
  grounding check         → UNDER_CONSTRAINED → clarify, else proceed

Entry point: classify(ctx) — called by orchestrator.
"""

from .affinity import try_route as _affinity_check
from .classifier import classify as _classify
from ..pipeline import PipelineContext
from ..commerce_intent import IntentResult


def classify(ctx: PipelineContext) -> dict | None:
    """Run all routing layers.

    Returns a terminal response dict (affinity hit or clarify reply),
    or None to continue to execution stage.
    """
    # Layer 1: Fast-path routing
    output = _affinity_check(ctx)
    if output is not None:
        return output

    # Layer 2: Intent classification
    _classify(ctx)

    # Layer 3: Unified constraint parsing + grounding
    return _build_and_check(ctx)


def _build_and_check(ctx: PipelineContext) -> dict | None:
    """Build SearchPlan and check grounding in one pass.

    UNDER_CONSTRAINED → clarify reply.  Otherwise store plan and proceed.
    """
    from ..contracts.search_plan import QueryFrame, normalize_query
    from ..nodes.search_plan_builder import build_plan

    intent = ctx.commerce_result if ctx.commerce_result else IntentResult(
        intent="search", confidence=0.0, fallback="chat",
    )
    frame = QueryFrame(
        raw=ctx.query,
        normalized=normalize_query(ctx.query),
        intent=intent,
    )
    plan = build_plan(frame)
    ctx.state.search_plan = plan

    if plan.state == "under_constrained":
        return _build_clarify_reply(ctx)

    return None


def _build_clarify_reply(ctx: PipelineContext) -> dict:
    """Build a clarify response for under-constrained queries."""
    from ..grounding import CLARIFY_TEMPLATES

    question = CLARIFY_TEMPLATES.get(
        "category",
        "能再说得具体一点吗？"
    )
    return {
        "reply": question,
        "intent": "clarify",
        "agent_type": "grounder",
        "confidence": 1.0,
        "blocks": [{
            "type": "clarify",
            "data": {"question": question, "missing_slot": "category", "options": []},
        }],
        "ranked_items": [],
        "tool_results": {},
        "explain": None,
        "retrieval": None,
        "show_budget_hint": False,
        "show_clarify_hint": True,
        "ui_state": "clarifying",
        "session_id": ctx.session_id,
        "query_type": ctx.query_type,
        "runtime": {"total_ms": ctx.elapsed_ms()},
    }
