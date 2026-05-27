"""
OrderAgent — main entry point for order lifecycle operations.

Pipeline (fixed, no branching):
  resolve_context → parse_intent → validate_transition →
  check_confirmation → execute_tool → build_response → persist_workflow
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from .state_machine import OrderStep, OrderSessionState, validate_transition
from .intent_parser import parse as parse_intent, OrderIntent
from .context_resolver import (
    resolve_reference, cancel_scope, allow_read_only_during_confirming,
)
from .confirmation_gate import generate_token, validate_token
from .tools import execute, requires_confirmation
from .response import (
    build_order_list, build_order_detail, build_confirm_prompt,
    build_logistics, build_refund_result, build_error, ResponsePayload,
)
from .repository import get_user_orders, get_order_detail, get_order_snapshot, _hash_snapshot
from .workflow_store import load as load_workflow, save as save_workflow, delete as delete_workflow

logger = logging.getLogger(__name__)


def run(query: str, user_id: int | None = None, session_id: str = "") -> dict:
    """
    Main entry point. Handles ONE turn of order conversation.

    Returns a dict compatible with the existing orchestrator response format.
    """
    # Default response
    if not user_id:
        return build_error("需要登录才能查询订单").to_dict()

    # ── Step 1: Resolve context ───────────────────────────
    wf = load_workflow(session_id)
    wf_state = OrderSessionState.from_workflow(wf) if wf else OrderSessionState(
        workflow_id=f"wf_{uuid.uuid4().hex[:16]}",
        current_step=OrderStep.IDLE,
    )

    # ── Step 2: Parse intent ──────────────────────────────
    parsed = parse_intent(query)

    # Handle references ("第二个")
    if parsed.is_reference:
        ref = resolve_reference(query, wf_state, wf_state.orders_snapshot, user_id=user_id, session_id=session_id)
        if ref["resolved"]:
            wf_state.selected_order_id = ref["order_id"]
            wf_state.current_step = OrderStep.SELECTED
            # Populate snapshot from "recent" DB query
            if ref.get("_orders"):
                wf_state.orders_snapshot = ref["_orders"]
            save_workflow(
                session_id=session_id, user_id=user_id,
                current_step=wf_state.current_step.value,
                selected_order_id=wf_state.selected_order_id,
                orders_snapshot=wf_state.orders_snapshot,
                snapshot_hash=wf_state.snapshot_hash,
                workflow_id=wf_state.workflow_id,
            )
            detail = get_order_detail(user_id, ref["order_id"])
            return build_order_detail(detail if detail else {"id": ref["order_id"]}).to_dict()
        else:
            return build_error(ref.get("error", "无法识别")).to_dict()

    # Handle decline ("算了")
    if parsed.intent == OrderIntent.DECLINE:
        cancel_result = cancel_scope(wf_state)
        if cancel_result["cancelled"]:
            wf_state.current_step = OrderStep(cancel_result["new_step"])
            save_workflow(
                session_id=session_id, user_id=user_id,
                current_step=wf_state.current_step.value,
                workflow_id=wf_state.workflow_id,
            )
        return build_error(cancel_result["message"]).to_dict()

    # Read-only ops during CONFIRMING (e.g., check logistics while confirming)
    if (wf_state.current_step == OrderStep.CONFIRMING
            and allow_read_only_during_confirming(parsed.intent)):
        result = execute(parsed.intent, user_id, wf_state.selected_order_id)
        return build_logistics(result).to_dict()

    # ── Step 3: Validate transition ───────────────────────
    target_step = _intent_to_step(parsed.intent)
    # Skip transition check for REFUND/CANCEL when no order selected —
    # auto-query will handle it downstream
    if target_step is not None and not (
        parsed.intent in (OrderIntent.REFUND, OrderIntent.CANCEL)
        and not wf_state.selected_order_id
    ):
        try:
            validate_transition(wf_state.current_step, target_step)
        except ValueError:
            return build_error(
                f"当前状态不支持此操作。你可以先退回上一步。"
            ).to_dict()

    # ── Step 4: Execute ───────────────────────────────────
    if parsed.intent == OrderIntent.QUERY_ORDERS:
        orders = execute("query_orders", user_id)
        wf_state.current_step = OrderStep.LISTING
        wf_state.orders_snapshot = orders
        snap = get_order_snapshot(user_id, orders[0]["id"]) if orders else None
        wf_state.snapshot_hash = _hash_snapshot(snap) if snap else None
        response = build_order_list(orders)

    elif parsed.intent == OrderIntent.ORDER_DETAIL:
        if not wf_state.selected_order_id:
            return build_error("请先选择订单").to_dict()
        detail = execute("order_detail", user_id, wf_state.selected_order_id)
        response = build_order_detail(detail) if detail else build_error("订单不存在")

    elif parsed.intent == OrderIntent.LOGISTICS:
        if not wf_state.selected_order_id:
            return build_error("请先选择订单").to_dict()
        result = execute("logistics", user_id, wf_state.selected_order_id)
        response = build_logistics(result)

    elif parsed.intent == OrderIntent.REFUND:
        if not wf_state.selected_order_id:
            # No order selected — auto-query orders first
            orders = execute("query_orders", user_id)
            if not orders:
                return build_error("你还没有订单，无法退款").to_dict()
            wf_state.current_step = OrderStep.LISTING
            wf_state.orders_snapshot = orders
            if len(orders) == 1:
                # Only one order — auto-select it
                wf_state.selected_order_id = orders[0]["id"]
                wf_state.current_step = OrderStep.SELECTED
            else:
                return build_order_list(orders).to_dict()
        if not wf_state.selected_order_id:
            return build_error("请先选择要退款的订单").to_dict()
        if requires_confirmation("request_refund"):
            snap = get_order_snapshot(user_id, wf_state.selected_order_id)
            snap_hash = _hash_snapshot(snap) if snap else ""
            token_info = generate_token(
                wf_state.workflow_id, wf_state.selected_order_id, "refund", snap_hash
            )
            wf_state.confirm_token = token_info["token"]
            wf_state.confirm_expires_at = token_info["expires_at"]
            wf_state.confirm_type = "refund"
            wf_state.snapshot_hash = snap_hash
            wf_state.current_step = OrderStep.CONFIRMING
            response = build_confirm_prompt("refund", wf_state.selected_order_id, token_info)
        else:
            result = execute("request_refund", user_id, wf_state.selected_order_id)
            response = build_refund_result(result)

    elif parsed.intent == OrderIntent.CANCEL:
        if not wf_state.selected_order_id:
            return build_error("请先选择订单").to_dict()
        if requires_confirmation("cancel_order"):
            snap = get_order_snapshot(user_id, wf_state.selected_order_id)
            snap_hash = _hash_snapshot(snap) if snap else ""
            token_info = generate_token(
                wf_state.workflow_id, wf_state.selected_order_id, "cancel", snap_hash
            )
            wf_state.confirm_token = token_info["token"]
            wf_state.confirm_expires_at = token_info["expires_at"]
            wf_state.confirm_type = "cancel"
            wf_state.snapshot_hash = snap_hash
            wf_state.current_step = OrderStep.CONFIRMING
            response = build_confirm_prompt("cancel", wf_state.selected_order_id, token_info)
        else:
            idem_key = f"cancel_{wf_state.workflow_id}_{uuid.uuid4().hex[:8]}"
            result = execute("cancel_order", user_id, wf_state.selected_order_id, idem_key)
            response = build_refund_result(result)

    elif parsed.intent == OrderIntent.CONFIRM:
        validation = validate_token(wf_state, wf_state.confirm_token,
                                    wf_state.orders_snapshot)
        if not validation["valid"]:
            return build_error(validation["error"] or "确认失败").to_dict()

        tool_name = "request_refund" if wf_state.confirm_type == "refund" else "cancel_order"
        idem_key = f"exec_{wf_state.workflow_id}_{uuid.uuid4().hex[:8]}"
        result = execute(tool_name, user_id, wf_state.selected_order_id, idempotency_key=idem_key)
        wf_state.confirm_token = None
        wf_state.confirm_type = None
        wf_state.confirm_expires_at = None
        wf_state.idempotency_key = idem_key
        wf_state.current_step = OrderStep.IDLE
        response = build_refund_result(result)

    else:
        # Not an order intent — signal orchestrator to fall back
        return {"_fallback": True, "reply": query}

    # ── Step 5: Persist ───────────────────────────────────
    save_workflow(
        session_id=session_id, user_id=user_id,
        current_step=wf_state.current_step.value,
        selected_order_id=wf_state.selected_order_id,
        confirm_type=wf_state.confirm_type,
        confirm_token=wf_state.confirm_token,
        confirm_expires_at=(
            datetime.fromisoformat(wf_state.confirm_expires_at)
            if wf_state.confirm_expires_at else None
        ),
        idempotency_key=wf_state.idempotency_key,
        orders_snapshot=wf_state.orders_snapshot,
        snapshot_hash=wf_state.snapshot_hash,
        workflow_id=wf_state.workflow_id,
    )

    result = response.to_dict()
    result["session_id"] = session_id
    result["agent_type"] = "order"
    return result


def _intent_to_step(intent: str) -> OrderStep | None:
    """Map intent to target OrderStep, or None if intent doesn't change step."""
    mapping = {
        OrderIntent.QUERY_ORDERS: OrderStep.LISTING,
        OrderIntent.REFUND:       OrderStep.CONFIRMING,
        OrderIntent.CANCEL:       OrderStep.CONFIRMING,
        OrderIntent.CONFIRM:      OrderStep.IDLE,
    }
    return mapping.get(intent)
