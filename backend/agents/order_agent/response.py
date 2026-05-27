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
    blocks: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)  # suggested next actions
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "reply": self.text,
            "intent": "order",
            "agent_type": "order",
            "blocks": self.blocks,
            "actions": self.actions,
            "metadata": self.metadata,
            "ui_state": "done",
        }


def build_order_list(orders: list[dict]) -> ResponsePayload:
    """Build response for order listing."""
    if not orders:
        return ResponsePayload(text="你还没有订单记录。")

    lines = ["你有以下订单："]
    blocks = []
    for i, o in enumerate(orders, 1):
        status_cn = _status_cn(o.get("status", ""))
        lines.append(f"{i}. [{status_cn}] {o.get('order_no', '')} — ¥{o.get('total_amount', '0')}")
        blocks.append({
            "type": "order_card",
            "data": {
                "index": i,
                "order_id": o.get("id"),
                "order_no": o.get("order_no"),
                "status": o.get("status"),
                "status_cn": status_cn,
                "amount": o.get("total_amount"),
                "created_at": o.get("created_at"),
            },
        })

    lines.append("\n回复数字编号查看详情，或选择「退款」「查物流」操作。")
    return ResponsePayload(
        text="\n".join(lines),
        blocks=blocks,
        actions=["退款", "查物流", "取消订单"],
        metadata={"count": len(blocks)},
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
