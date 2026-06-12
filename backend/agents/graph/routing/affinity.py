"""
Affinity Router — fast-path routing without LLM calls.

Priority chain (each can produce a terminal response):
  P1  StructuredRouter — pure DB lookup (order/cart history)
  P2  Active OrderWorkflow — in-progress cancel/refund flow
  P3  Block-based affinity — recent assistant UI blocks determine workflow owner

If none fire, returns None → caller falls through to classifier.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from ..pipeline import PipelineContext, AgentCapability

logger = logging.getLogger(__name__)

MAX_AFFINITY_AGE = 300  # seconds — ignore blocks older than this


@dataclass
class ActionBlock:
    """A UI block from an assistant message — event source for routing."""
    type: str
    data: dict = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class ConversationActionContext:
    """Snapshot of recent assistant actions, derived from UI blocks only."""
    active_blocks: list[ActionBlock] = field(default_factory=list)

    @property
    def workflow_phase(self) -> str | None:
        if not self.active_blocks:
            return None
        t = self.active_blocks[0].type
        if t == "order_created_card":
            return "completed"
        if t == "confirm_dialog":
            return "awaiting_confirm"
        if t in ("product_card", "cart_card"):
            return "active"
        return None


_AFFINITY_TABLE: dict[str, AgentCapability] = {
    "order_created_card": AgentCapability.ORDER,
    "confirm_dialog":     AgentCapability.PURCHASE,
    "cart_card":          AgentCapability.CART,
}


# ── Public API ───────────────────────────────────────────────────


def try_route(ctx: PipelineContext) -> dict | None:
    """Run all fast-path routing layers.

    Returns a response dict if a layer produces a terminal result,
    or None to continue to classifier.
    """
    output = _structured_route(ctx)
    if output:
        return output

    output = _affinity_route(ctx)
    if output:
        return output

    return None


# ── P1: StructuredRouter ────────────────────────────────────────


def _structured_route(ctx: PipelineContext) -> dict | None:
    """Order/cart history — direct SQL lookup, skip entire graph."""
    if not ctx.user_id:
        return None

    from ..structured_router import StructuredRouter, StructuredIntent
    sr = StructuredRouter()
    s_intent = sr.detect(ctx.query, ctx.user_id)
    if s_intent == StructuredIntent.NONE:
        return None

    result = sr.execute(s_intent, ctx.user_id, ctx.session_id)
    return {
        "reply": result.reply,
        "intent": "structured",
        "confidence": 1.0,
        "agent_type": s_intent.value,
        "blocks": [],
        "ranked_items": result.data.get("items", []),
        "tool_results": {},
        "session_id": ctx.session_id,
        "query_type": ctx.query_type,
        "runtime": {
            "phases": [{"phase": "structured", "label": "结构化查询", "status": "ok", "ms": ctx.elapsed_ms()}],
            "total_ms": ctx.elapsed_ms(),
        },
        "explain": None, "retrieval": None,
        "show_budget_hint": False, "show_clarify_hint": False,
    }


# ── P2/P3: Workflow + Block affinity ────────────────────────────


def _affinity_route(ctx: PipelineContext) -> dict | None:
    """WorkflowAffinity — block-driven + active workflow routing."""
    if not ctx.session_id:
        return None

    # P2 — Active OrderWorkflow
    # Skip if query contains a product reference — user is starting
    # a new action ("买第一个"), not continuing an order workflow.
    if not _has_product_reference(ctx.query):
        from agents.order.workflow_store import load as load_owf
        owf = load_owf(ctx.session_id)
        if owf and owf.current_step != "idle":
            return _dispatch_agent(ctx, AgentCapability.ORDER)

    # P3 — Block-based affinity (event-sourced)
    actx = build_action_context(ctx.session_id)
    capability = route_by_affinity(actx, ctx.query)
    if capability:
        return _dispatch_agent(ctx, capability)

    return None


def _dispatch_agent(ctx: PipelineContext, capability: AgentCapability) -> dict | None:
    """Dispatch via execution registry — single dispatch path for the whole system.

    Uses execution.dispatch() which calls AgentExecutor.execute() through the
    typed registry.  This is the same path the execution stage uses — no duplication.
    """
    from ..pipeline import AgentContext
    from ..execution import dispatch as exec_dispatch

    agent_ctx = AgentContext.from_pipeline(ctx)
    agent_result = exec_dispatch(capability, agent_ctx)
    if agent_result.status == "success" and agent_result.response:
        return agent_result.response
    return None


# ── Action context builders ─────────────────────────────────────


def build_action_context(session_id: str) -> ConversationActionContext:
    """Scan last 3 assistant messages for blocks, with TTL enforcement."""
    if not session_id:
        return ConversationActionContext()

    try:
        from agents.models import AgentConversation
        from django.utils import timezone

        now = timezone.now()
        msgs = (
            AgentConversation.objects
            .filter(session_id=session_id, role="assistant")
            .order_by("-created_at")[:3]
        )

        blocks: list[ActionBlock] = []
        for msg in msgs:
            if not msg.metadata:
                continue
            age = (now - msg.created_at).total_seconds()
            if age > MAX_AFFINITY_AGE:
                continue

            for b in msg.metadata.get("blocks", []):
                blocks.append(ActionBlock(
                    type=b.get("type", ""),
                    data=b.get("data", {}),
                    created_at=msg.created_at,
                ))

        return ConversationActionContext(active_blocks=blocks)
    except Exception:
        logger.warning("build_action_context failed for session=%s", session_id, exc_info=True)
        return ConversationActionContext()


def route_by_affinity(ctx: ConversationActionContext, query: str) -> AgentCapability | None:
    """Return agent capability if workflow affinity exists, or None.

    P0 — strong intent interrupts any affinity (user changed topic).
    P1 — first matching block type in newest-first order wins.
    Unknown block types are logged at DEBUG level — not an error,
    many block types (message, clarify, explain) are routing-irrelevant.
    """
    if not ctx.active_blocks:
        return None

    # P0 — explicit strong intent breaks affinity
    from ..state_router import has_strong_intent
    if has_strong_intent(query):
        return None

    # P1 — first matching block
    for block in ctx.active_blocks:
        capability = _AFFINITY_TABLE.get(block.type)
        if capability:
            return capability
        if block.type not in ("message", "clarify", "explain", "report", "metric"):
            logger.debug("Block type '%s' not in affinity table, falling through", block.type)

    return None

def _has_product_reference(query: str) -> bool:
    """True if query contains an ordinal reference ("第一个", "买第二个")."""
    import re
    return bool(re.search(r'第\s*[一二两三四五六七八九十\d]+\s*[个款]', query))
