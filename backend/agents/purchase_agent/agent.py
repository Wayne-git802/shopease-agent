"""
PurchaseAgent — lightweight purchase flow.

Pipeline:
  resolve_product_id → validate(price+stock) → confirm_prompt → create_order

No state machine persistence. No TTL. No token. Pure function: parse → validate → buy.
"""

from __future__ import annotations

import logging

from .intent_parser import parse as parse_intent, PurchaseIntent
from orders.models import Order, OrderStatus

logger = logging.getLogger(__name__)


def run(query: str, user_id: int | None = None, session_id: str = "") -> dict:
    """Main entry point. Handles ONE turn of purchase conversation."""
    if not user_id:
        return _error("需要登录才能下单")

    parsed = parse_intent(query)

    # Decline
    if parsed.intent == PurchaseIntent.DECLINE:
        return _error("已取消")

    if parsed.intent == PurchaseIntent.OTHER:
        return {"_fallback": True, "reply": query}

    # ── Resolve product_id ────────────────────────────────
    product_id = _resolve_product_id(session_id, parsed)
    if not product_id:
        return _error("请先搜索或浏览商品，然后告诉我买第几个")

    # ── Validate: price + stock ────────────────────────────
    product = _get_product(product_id)
    if not product:
        return _error("商品不存在或已下架")

    price = float(product.get("price", 0))
    stock = product.get("stock", 0)
    name = product.get("name", f"商品#{product_id}")

    if stock <= 0:
        return _error("该商品已售罄")

    # ── Confirm or Execute ──────────────────────────────────
    if parsed.intent == PurchaseIntent.CONFIRM:
        return _create_order(user_id, product_id, name, price)

    # Show confirmation prompt
    return {
        "reply": f"确认购买「{name}」¥{price}？回复「确认」下单，回复「算了」取消。",
        "intent": "purchase",
        "agent_type": "purchase",
        "blocks": [{
            "type": "confirm_dialog",
            "data": {"product_id": product_id, "name": name, "price": price, "action": "purchase"},
        }],
        "ui_state": "confirming",
    }


def _resolve_product_id(session_id: str, parsed) -> int | None:
    """Resolve product_id from previous CommerceAgent blocks."""
    # Try reference from query
    if parsed.reference_type == "index" and isinstance(parsed.reference_value, int):
        return _lookup_by_index(session_id, parsed.reference_value)

    # Try "买这个" — get most recent product from blocks
    return _lookup_latest(session_id)


def _lookup_by_index(session_id: str, index: int) -> int | None:
    """Look up product by index from recent product_card blocks."""
    blocks = _get_recent_blocks(session_id, block_type="product_card")
    for block in blocks:
        data = block.get("data", {})
        products = data.get("products", [data])
        if isinstance(products, list) and 0 <= index < len(products):
            p = products[index]
            return p.get("product_id") or p.get("id")
    return None


def _lookup_latest(session_id: str) -> int | None:
    """Get the most recent product from blocks."""
    return _lookup_by_index(session_id, 0)


def _get_recent_blocks(session_id: str, block_type: str | None = None) -> list[dict]:
    """Get blocks from recent assistant messages, optionally filtered by type.
    
    Scans last 5 messages to find blocks — purchase confirm may be in a
    different message from product_card.
    """
    try:
        from agents.models import AgentConversation
        msgs = (
            AgentConversation.objects
            .filter(session_id=session_id, role="assistant")
            .order_by("-created_at")[:5]
        )
        all_blocks = []
        for msg in msgs:
            if msg.metadata:
                blocks = msg.metadata.get("blocks", [])
                if block_type:
                    blocks = [b for b in blocks if b.get("type") == block_type]
                all_blocks.extend(blocks)
        return all_blocks
    except Exception:
        return []


def _get_product(product_id: int) -> dict | None:
    """Get product info from DB."""
    try:
        from products.models import Product, Inventory
        p = Product.objects.filter(id=product_id, is_active=True).first()
        if not p:
            return None
        inv = Inventory.objects.filter(product_id=p.id).first()
        return {
            "id": p.id,
            "name": p.name,
            "price": float(p.price),
            "stock": inv.quantity if inv else 0,
            "category": p.category.name if p.category else "",
        }
    except Exception:
        return None


def _create_order(user_id: int, product_id: int, name: str, price: float) -> dict:
    """Create an order directly."""
    try:
        from products.models import Product
        from django.contrib.auth import get_user_model
        User = get_user_model()

        product = Product.objects.get(id=product_id, is_active=True)
        user = User.objects.get(id=user_id)

        # Create order
        order = Order.objects.create(
            user=user,
            total_amount=price,
            status=OrderStatus.PAID,
            address="",
            receiver_name="",
            receiver_phone="",
        )
        # Attach order item
        from orders.models import OrderItem
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=1,
            price=price,
        )

        return {
            "reply": f"下单成功！订单号 {order.order_no}，金额 ¥{price}。",
            "intent": "purchase",
            "agent_type": "purchase",
            "blocks": [{
                "type": "order_created_card",
                "data": {
                    "order_id": order.id,
                    "order_no": order.order_no,
                    "product_name": name,
                    "amount": str(price),
                    "status": "paid",
                },
            }],
            "ui_state": "done",
        }
    except Exception as e:
        logger.exception("create_order failed")
        return _error(f"下单失败: {e}")


def _error(message: str) -> dict:
    return {
        "reply": message,
        "intent": "purchase",
        "agent_type": "purchase",
        "blocks": [],
        "ui_state": "done",
    }
