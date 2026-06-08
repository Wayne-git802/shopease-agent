"""
Repository — DB operations for product and order.

Provides get_product, create_order, and get_cart_items backed by
products.models and orders.models.
"""

from __future__ import annotations

import logging

from products.models import Product, Inventory
from orders.models import Order, OrderItem, OrderStatus

logger = logging.getLogger(__name__)


def get_product(product_id: int) -> dict | None:
    """Fetch product info: id, name, price, stock, category.

    Returns None if the product does not exist or is inactive.
    """
    try:
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
        logger.exception("get_product(%d) failed", product_id)
        return None


def create_order(
    user_id: int,
    product_id: int,
    name: str,
    price: float,
) -> dict:
    """Create an Order with one OrderItem. Uses Order.create_direct.

    Returns:
        {"order_id": int, "order_no": str, "product_name": str, "amount": float}
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    user = User.objects.get(id=user_id)

    order = Order.create_direct(
        user=user,
        product_id=product_id,
        quantity=1,
        address="AI Agent Purchase",
        receiver_name=user.username or "User",
        receiver_phone="00000000000",
        remark="",
    )

    return {
        "order_id": order.id,
        "order_no": order.order_no,
        "product_name": name,
        "amount": float(price),
    }


def get_cart_items(user_id: int) -> list[dict]:
    """Fetch the user's cart items for checkout flow.

    Returns a list of dicts with product_id, name, price, quantity.
    """
    from orders.models import Cart

    try:
        carts = Cart.objects.filter(
            user_id=user_id,
        ).select_related("product")

        return [
            {
                "product_id": c.product_id,
                "name": c.product.name,
                "price": float(c.product.price),
                "quantity": c.quantity,
            }
            for c in carts
        ]
    except Exception:
        logger.exception("get_cart_items(%d) failed", user_id)
        return []
