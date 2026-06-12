"""
Response Builder — structured output for OrderAgent.

Produces ResponsePayload with text, blocks, actions, and metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResponsePayload:
    text: str
    reply: str = ""                     # alias for text, used by frontend
    blocks: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)  # suggested next actions
    metadata: dict = field(default_factory=dict)
    ui_state: str = "done"              # cognitive UI state

    def __post_init__(self):
        if not self.reply:
            self.reply = self.text

    def to_dict(self) -> dict:
        return {
            "reply": self.reply or self.text,
            "intent": "order",
            "agent_type": "order",
            "blocks": self.blocks,
            "actions": self.actions,
            "metadata": self.metadata,
            "ui_state": self.ui_state,
        }


def build_order_list(orders: list[dict]) -> ResponsePayload:
    """Build order card blocks for each order."""
    if not orders:
        return ResponsePayload(text="你还没有订单记录。")

    blocks = []
    for order in orders:
        blocks.append({
            "type": "order_card",
            "data": {
                "order_id": order["id"],
                "product_name": order.get("product_name", order.get("name", "")),
                "price": order.get("price", order.get("total_amount", 0)),
                "status": order.get("status", ""),
                "created_at": order.get("created_at", ""),
            },
        })

    reply = f"为你找到 {len(orders)} 个订单，请选择要操作的订单："
    return ResponsePayload(
        text=reply,
        reply=reply,
        blocks=blocks,
        actions=["退款", "查物流", "取消订单"],
        metadata={"count": len(blocks)},
        ui_state="listing",
    )


def build_order_detail(order: dict) -> ResponsePayload:
    """Build response for single order detail."""
    status = _status_cn(order.get("status", ""))
    return ResponsePayload(
        text=f"订单 {order.get('order_no', '')}\n"
             f"状态：{status}\n"
             f"金额：¥{order.get('total_amount', '0')}\n"
             f"地址：{order.get('address', '')}\n"
             f"收件人：{order.get('receiver_name', '')} {order.get('receiver_phone', '')}",
        blocks=[{"type": "order_card", "data": {"order_id": order.get("id"), "status": order.get("status"), "status_cn": status}}],
        actions=["退款", "查物流"] if order.get("status") in ("paid", "shipped") else [],
    )


def build_confirm_prompt(confirm_type: str, order_id: int, token_info: dict) -> ResponsePayload:
    """Build confirmation prompt."""
    label = "退款" if confirm_type == "refund" else "取消订单"
    return ResponsePayload(
        text=f"确认{label}？回复「确认」继续，回复「算了」取消。（{token_info.get('expires_at', '')[:16]} 前有效）",
        blocks=[{"type": "confirm_dialog", "data": {"confirm_type": confirm_type, "order_id": order_id}}],
        actions=["确认", "算了"],
        metadata={"confirm_token": token_info.get("token"), "confirm_type": confirm_type},
    )


def build_logistics(logistics: dict) -> ResponsePayload:
    """Build logistics response."""
    if not logistics.get("found"):
        return ResponsePayload(text=logistics.get("error", "订单不存在"))
    return ResponsePayload(
        text=f"订单 {logistics.get('order_no', '')}\n{logistics.get('description', '')}",
        blocks=[{"type": "logistics_info", "data": logistics}],
    )


def build_refund_result(result: dict) -> ResponsePayload:
    """Build refund/cancel result."""
    if result.get("ok"):
        return ResponsePayload(text=f"已提交，退款单号 {result.get('refund_no', result.get('order_no', ''))}，等待处理。")
    return ResponsePayload(text=result.get("error", "操作失败，请稍后重试。"))


def build_error(message: str) -> ResponsePayload:
    return ResponsePayload(text=message)


def _status_cn(status: str) -> str:
    return {
        "paid": "已支付", "shipped": "已发货", "completed": "已完成",
        "cancelled": "已取消", "refunded": "已退款",
    }.get(status, status)
