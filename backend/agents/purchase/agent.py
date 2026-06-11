"""
PurchaseAgent — complete state-machine-driven purchase pipeline.

Pipeline:
  intent_parser → reference_resolver → state_machine → confirmation_gate
  → repository → response

The orchestrator calls run() for the initial purchase intent, then
handle_confirm() when the user replies to the confirmation prompt.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from . import workflow_store
from . import confirmation_gate
from . import repository
from . import response
from .intent_parser import parse as parse_intent, PurchaseIntent
from .state_machine import (
    PurchaseStep,
    PurchaseSessionState,
    validate_transition,
)
from .response import build_confirm, build_success, build_error, build_decline

logger = logging.getLogger(__name__)


def _run(
    query: str,
    user_id: int | None = None,
    session_id: str = "",
    display_id: str = "",
    resolved_ref: object = None,  # ResolvedReference from routing layer
) -> dict:
    """Internal implementation.  External callers use PurchaseAgent.execute()."""

    # 1. Auth gate
    if not user_id:
        return build_error("需要登录才能下单")

    # 2. Load state from DB
    state = workflow_store.load(session_id)
    if not state:
        state = PurchaseSessionState(workflow_id=f"wf_{uuid4().hex[:16]}")

    # 3. Parse intent
    parsed = parse_intent(query)
    if parsed.intent == PurchaseIntent.DECLINE:
        return build_decline()
    if parsed.intent == PurchaseIntent.OTHER:
        return {"_fallback": True}

    # 4. Resolve product reference — prefer routing layer's resolved ref
    from agents.graph.routing.reference_resolver import ResolvedReference as RoutingRef
    if resolved_ref is not None and getattr(resolved_ref, 'product_id', 0):
        ref = ResolvedReference(
            source="routing",
            product_id=resolved_ref.product_id,
            confidence=0.95,
            name=getattr(resolved_ref, 'product_name', ''),
        )
    else:
        from agents.graph.reference_resolver import resolve as resolve_ref
        ref = resolve_ref(
            session_id=session_id,
            display_id=display_id,
            query=query,
            reference_type=parsed.reference_type or "",
            reference_value=parsed.reference_value,
        )
    if not ref.source or not ref.product_id:
        return build_error("请先搜索或浏览商品，然后告诉我买第几个")

    # 5. Validate transition
    validate_transition(state.current_step, PurchaseStep.VIEWING)

    # 6. Get product + snapshot
    product = repository.get_product(ref.product_id)
    if not product:
        return build_error("商品不存在或已下架")
    if product["stock"] <= 0:
        return build_error("该商品已售罄")

    # 7. Generate confirmation token
    token_dict = confirmation_gate.generate_token(
        state.workflow_id,
        ref.product_id,
        "purchase",
        {"price": product["price"], "stock": product["stock"]},
    )

    # 8. Update state to CONFIRMING
    state.current_step = PurchaseStep.CONFIRMING
    state.selected_product_id = ref.product_id
    state.confirm_token = token_dict["token"]
    state.confirm_expires_at = token_dict["expires_at"]
    state.snapshot_hash = token_dict["snapshot_hash"]
    workflow_store.save(session_id, state)

    # 9. Show confirmation
    return build_confirm(ref.product_id, product["name"], product["price"])


def handle_confirm(
    query: str,
    user_id: int | None = None,
    session_id: str = "",
) -> dict:
    """Handle the confirmation step (user says '确认' / '算了').

    Called when the orchestrator detects the user is in the purchase
    confirming phase.
    """
    state = workflow_store.load(session_id)
    if not state:
        return build_error("没有待确认的操作")

    parsed = parse_intent(query)
    if parsed.intent == PurchaseIntent.DECLINE:
        workflow_store.delete(session_id)
        return build_decline()

    # Validate token
    product = repository.get_product(state.selected_product_id)
    if not product:
        return build_error("商品不存在")

    result = confirmation_gate.validate_token(
        state,
        state.confirm_token,
        {"price": product["price"], "stock": product["stock"]},
    )
    if not result["valid"]:
        workflow_store.delete(session_id)
        return build_error(result["error"])

    # Consume token
    confirmation_gate.consume_token(state)
    workflow_store.save(session_id, state)

    # Execute order
    order = repository.create_order(
        user_id,
        state.selected_product_id,
        product["name"],
        product["price"],
    )

    # Transition to PURCHASED
    state.current_step = PurchaseStep.PURCHASED
    workflow_store.save(session_id, state)

    return build_success(
        order["order_id"],
        order["order_no"],
        product["name"],
        product["price"],
    )


# ═══════════════════════════════════════════════════════════════
# AgentExecutor interface (Phase 4)
# ═══════════════════════════════════════════════════════════════

from agents.graph.pipeline import AgentResult, AgentCapability, Handoff, PipelineContext, AgentContext


class PurchaseAgent:
    """Purchase flow agent — implements AgentExecutor protocol.

    Owns the confirm-or-run decision that was previously in the executor wrapper.
    Reads SharedView for cart_snapshot when entering from CartAgent handoff.
    """

    capability = AgentCapability.PURCHASE
    priority = 10

    def can_handle(self, ctx: PipelineContext) -> bool:
        commerce = ctx.commerce_result
        return bool(commerce and commerce.intent == "purchase" and commerce.confidence >= 0.3)

    def execute(self, ctx: AgentContext) -> AgentResult:
        from .workflow_store import load as load_wf
        from .state_machine import PurchaseStep

        # Active confirmation workflow → handle_confirm
        wf = load_wf(ctx.session_id) if ctx.session_id else None
        if wf and wf.current_step == PurchaseStep.CONFIRMING:
            result = handle_confirm(query=ctx.query, user_id=ctx.user_id, session_id=ctx.session_id)
        else:
            # Read shared view for cart snapshot (from CartAgent handoff)
            view = ctx.memory.get_shared_view(ctx.session_id)
            # Inject cart snapshot into result so display layer can show it
            result = _run(
                query=ctx.query, user_id=ctx.user_id,
                session_id=ctx.session_id, display_id=ctx.display_id,
            )
            if view.cart_snapshot and not result.get("_fallback"):
                result.setdefault("cart_snapshot", view.cart_snapshot)

        if result.get("_fallback"):
            return AgentResult(status="fallback")
        return AgentResult(status="success", response=result)


purchase_agent = PurchaseAgent()
