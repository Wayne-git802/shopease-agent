"""
Context Resolver — scope-aware reference resolution for OrderAgent.

Handles:
  - "第二个" → resolve to actual order_id from current snapshot
  - "刚才下单的" → auto-query DB for most recent order (works even IDLE)
  - Snapshot TTL validation (10 min for listing)
  - Scoped cancel (只取消当前 workflow，不清 commerce state)
  - Allow read_only ops during CONFIRMING (check logistics without resetting)
"""

from __future__ import annotations

from .state_machine import OrderStep, OrderSessionState


def resolve_reference(
    query: str,
    wf_state: OrderSessionState | None,
    visible_orders: list[dict],
    user_id: int | None = None,
) -> dict:
    """
    Resolve a reference query against the current context.

    Returns:
        {"resolved": bool, "order_id": int|None, "error": str|None, "matched_by": str|None,
         "_orders": list|None}  — _orders only set for "recent" references
    """
    from .intent_parser import parse, OrderIntent

    parsed = parse(query)
    if not parsed.is_reference:
        return {"resolved": False, "order_id": None, "error": None}

    # ── "recent" reference — auto-query DB, works even when IDLE ──
    if parsed.reference_value == "recent":
        if not user_id:
            return {"resolved": False, "order_id": None, "error": "需要登录"}
        from .repository import get_user_orders
        orders = get_user_orders(user_id)
        if not orders:
            return {"resolved": False, "order_id": None, "error": "你还没有订单"}
        oid = orders[0].get("id") or orders[0].get("order_id")
        return {"resolved": True, "order_id": oid, "matched_by": "最近订单",
                "_orders": orders}

    # ── All other references need active workflow context ──
    if not wf_state or wf_state.current_step == OrderStep.IDLE:
        return {"resolved": False, "order_id": None, "error": "当前没有活跃的订单上下文，请先查询订单"}

    # Validate snapshot TTL
    if wf_state.current_step == OrderStep.LISTING and wf_state.is_expired():
        return {"resolved": False, "order_id": None, "error": "订单列表已过期（超过10分钟），请重新查询"}

    orders = wf_state.orders_snapshot or visible_orders
    if not orders:
        return {"resolved": False, "order_id": None, "error": "当前没有订单数据"}

    # Index-based reference ("第二个")
    if parsed.reference_type == "index":
        idx = parsed.reference_value
        if isinstance(idx, int) and 0 <= idx < len(orders):
            oid = orders[idx].get("id") or orders[idx].get("order_id")
            return {"resolved": True, "order_id": oid, "matched_by": f"第{idx+1}个订单"}

    # Match-based reference ("那个退款的")
    if parsed.reference_type == "match" and parsed.reference_value == "refund":
        refundable = [o for o in orders if o.get("status") in ("paid", "shipped")]
        if len(refundable) == 1:
            oid = refundable[0].get("id") or refundable[0].get("order_id")
            return {"resolved": True, "order_id": oid, "matched_by": "可退款订单"}
        elif len(refundable) > 1:
            return {"resolved": False, "order_id": None,
                    "error": f"有 {len(refundable)} 个可退款订单，请指明第几个"}

    if parsed.reference_type == "match" and parsed.reference_value == "latest":
        if orders:
            oid = orders[0].get("id") or orders[0].get("order_id")
            return {"resolved": True, "order_id": oid, "matched_by": "最新订单"}

    return {"resolved": False, "order_id": None, "error": "无法确定你指的是哪个订单"}


def cancel_scope(
    wf_state: OrderSessionState | None,
) -> dict:
    """
    Handle "算了" / "不用了" — scoped to current workflow only.

    Returns:
        {"cancelled": bool, "new_step": str, "message": str}
    """
    if not wf_state or wf_state.current_step == OrderStep.IDLE:
        return {"cancelled": False, "new_step": "idle", "message": "当前没有进行中的操作"}

    if wf_state.current_step == OrderStep.CONFIRMING:
        return {"cancelled": True, "new_step": "selected",
                "message": "已取消确认，你可以选择其他操作"}

    if wf_state.current_step in (OrderStep.LISTING, OrderStep.SELECTED):
        return {"cancelled": True, "new_step": "idle",
                "message": "已退出订单查询"}

    return {"cancelled": False, "new_step": wf_state.current_step.value,
            "message": "当前操作不需要取消"}


def allow_read_only_during_confirming(intent: str) -> bool:
    """Check if this intent is a read-only operation allowed during CONFIRMING."""
    from .intent_parser import OrderIntent
    return intent in (OrderIntent.LOGISTICS, OrderIntent.ORDER_DETAIL, OrderIntent.QUERY_ORDERS)
