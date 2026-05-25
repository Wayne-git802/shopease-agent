"""
Order Node — deterministic order operations (no LLM).

I/O Contract:
  Input:  OrderNodeInput  (action, order_id, user_id)
  Output: OrderNodeOutput (result, status)
  side_effect: DB reads only (deterministic)
"""
import time

from ..state import AgentState, NodeTrace
from ..contracts import OrderNodeInput, OrderNodeOutput


def order_node(state: AgentState) -> AgentState:
    """Handle order queries — fully deterministic, no LLM."""
    start = time.time()

    action = state.parallel_results.get("order_action", "status")
    order_id = state.parallel_results.get("order_id")

    result = {"status": "ok", "data": {}}

    if not state.user_id:
        result["status"] = "error"
        result["error"] = "需要登录才能查询订单"

    elif action == "status":
        import django; django.setup()
        from orders.models import Order
        if order_id:
            try:
                order = Order.objects.get(id=order_id, user_id=state.user_id)
                result["data"] = {
                    "order_no": order.order_no,
                    "status": order.status,
                    "total": float(order.total_amount),
                    "created": order.created_at.isoformat(),
                }
            except Order.DoesNotExist:
                result["status"] = "error"
                result["error"] = "订单不存在"

    elif action == "cancel":
        import django; django.setup()
        from orders.models import Order, OrderStatus
        if order_id:
            try:
                order = Order.objects.get(id=order_id, user_id=state.user_id)
                if order.status == OrderStatus.PAID:
                    order.status = OrderStatus.CANCELLED
                    order.save()
                    result["data"] = {"order_no": order.order_no, "status": "cancelled"}
                    result["status"] = "ok"
                else:
                    result["status"] = "error"
                    result["error"] = f"订单状态 {order.status} 不可取消"
            except Order.DoesNotExist:
                result["status"] = "error"
                result["error"] = "订单不存在"

    state.tool_results["order"] = result
    state.current_node = "order"
    state.ui_message = "正在查询订单…"
    state.steps_done.append("order")

    state.trace.append(NodeTrace(
        node_name="order",
        model_name="",
        latency_ms=int((time.time() - start) * 1000),
    ))

    return state
