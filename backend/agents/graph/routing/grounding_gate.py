"""
Grounding Gate — executability check (orchestration layer).

References the pure grounding engine in graph/grounding.py.
This layer handles:
  - Session-aware skip logic (recent product_card + no new anchor)
  - Clarify depth tracking
  - Clarify reply building + session persistence

Does NOT duplicate grounding logic — ground() and plan() live in graph/grounding.py.
"""

from __future__ import annotations

import logging

from ..pipeline import PipelineContext

logger = logging.getLogger(__name__)


def check(ctx: PipelineContext) -> dict | None:
    """Run grounding gate. Returns a clarify response dict, or None to proceed.

    Only applies to search/recommend/explore intents.
    """
    commerce = ctx.commerce_result
    if not commerce:
        return None
    if commerce.intent not in ("search", "recommend", "explore"):
        return None

    from ..grounding import ground, plan, build_clarify_reply
    from ..session_memory import put_conv_state
    from ..preprocessor import ConversationState

    slots = ground(ctx.query)

    # Skip when user interacts with displayed results (no new category anchor)
    if ctx.session_id:
        from .affinity import build_action_context
        actx = build_action_context(ctx.session_id)
        has_cards = any(b.type == "product_card" for b in actx.active_blocks)
        has_new_anchor = bool(slots.get("category"))
        if has_cards and not has_new_anchor:
            return None  # skip grounding, proceed normally

    clarify_depth = (
        getattr(ctx.conv_state.dialogue, '_clarify_depth', 0)
        if ctx.conv_state else 0
    )
    gr = plan(slots, depth=clarify_depth)

    if gr.state == "needs_category":
        reply = build_clarify_reply(gr.missing_slot or "category")
        reply["session_id"] = ctx.session_id
        reply["query_type"] = ctx.query_type
        reply["runtime"] = {"total_ms": ctx.elapsed_ms()}

        if ctx.session_id:
            cs = ctx.conv_state or ConversationState(
                session_id=ctx.session_id,
                original_query=ctx.query,
                pending_question=reply["reply"],
            )
            cs.dialogue.last_user_query = ctx.query
            cs.dialogue.expects_followup = True
            cs.dialogue._clarify_depth = clarify_depth + 1
            put_conv_state(cs)

        return reply

    return None
