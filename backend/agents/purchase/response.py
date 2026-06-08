"""
Response builders — structured dict responses for PurchaseAgent.

Each function returns a dict compatible with the agent orchestrator.
"""

from __future__ import annotations


def build_confirm(product_id: int, name: str, price: float) -> dict:
    """Build a confirmation prompt with a confirm_dialog block."""
    return {
        "reply": f"确认购买「{name}」¥{price}？回复「确认」下单，回复「算了」取消。",
        "intent": "purchase",
        "agent_type": "purchase",
        "blocks": [
            {
                "type": "confirm_dialog",
                "data": {
                    "product_id": product_id,
                    "name": name,
                    "price": price,
                    "action": "purchase",
                },
            }
        ],
        "ui_state": "confirming",
    }


def build_success(
    order_id: int,
    order_no: str,
    name: str,
    price: float,
) -> dict:
    """Build an order-created response with an order_created_card block."""
    return {
        "reply": f"下单成功！订单号 {order_no}，金额 ¥{price}。",
        "intent": "purchase",
        "agent_type": "purchase",
        "blocks": [
            {
                "type": "order_created_card",
                "data": {
                    "order_id": order_id,
                    "order_no": order_no,
                    "product_name": name,
                    "amount": str(price),
                    "status": "paid",
                },
            }
        ],
        "ui_state": "done",
    }


def build_error(message: str) -> dict:
    """Build an error response."""
    return {
        "reply": message,
        "intent": "purchase",
        "agent_type": "purchase",
        "blocks": [],
        "ui_state": "done",
    }


def build_decline() -> dict:
    """Build a user-cancelled response."""
    return {
        "reply": "已取消。",
        "intent": "purchase",
        "agent_type": "purchase",
        "blocks": [],
        "ui_state": "done",
    }
