"""
Cart Repository — data access layer for Cart operations.

All DB operations for the shopping cart go through here.
Uses upsert semantics: add_to_cart increments quantity if the
user-product row already exists.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from django.db import transaction

from orders.models import Cart

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Write operations
# ═══════════════════════════════════════════════════════════

def add_to_cart(
    user_id: int,
    product_id: int,
    request_id: str = "",
    quantity: int = 1,
) -> dict:
    """Add a product to the user's cart with upsert semantics.

    If the row already exists (same user + product), quantity is
    incremented rather than creating a duplicate row.
    """
    if not request_id:
        request_id = uuid4().hex[:16]

    with transaction.atomic():
        row, created = Cart.objects.get_or_create(
            user_id=user_id,
            product_id=product_id,
            defaults={"quantity": quantity},
        )

        if not created:
            # Row already existed — increment
            row.quantity += quantity
            row.save()

        logger.info(
            "cart add_to_cart request_id=%s user=%s product=%s qty=%s action=%s",
            request_id,
            user_id,
            product_id,
            row.quantity,
            "created" if created else "updated",
        )

    return {
        "status": "ok",
        "product_id": product_id,
        "quantity": row.quantity,
        "name": row.product.name,
        "request_id": request_id,
    }


def update_quantity(
    user_id: int,
    product_id: int,
    quantity: int,
) -> dict:
    """Update the quantity of a cart item.  Removes the item if quantity <= 0."""
    if quantity <= 0:
        return remove_item(user_id, product_id)

    try:
        row = Cart.objects.get(user_id=user_id, product_id=product_id)
    except Cart.DoesNotExist:
        return {"status": "error", "product_id": product_id, "error": "Cart item not found"}

    row.quantity = quantity
    row.save()

    return {
        "status": "ok",
        "product_id": product_id,
        "new_quantity": row.quantity,
    }


def remove_item(user_id: int, product_id: int) -> dict:
    """Remove a single product from the cart."""
    deleted, _ = Cart.objects.filter(
        user_id=user_id, product_id=product_id,
    ).delete()

    return {
        "status": "ok",
        "removed": product_id,
    }


# ═══════════════════════════════════════════════════════════
# Read operations
# ═══════════════════════════════════════════════════════════

def get_cart_items(user_id: int) -> list[dict]:
    """Return all items in the user's cart."""
    rows = (
        Cart.objects
        .filter(user_id=user_id)
        .select_related("product")
    )

    return [
        {
            "product_id": r.product_id,
            "name": r.product.name,
            "price": str(r.product.price),
            "quantity": r.quantity,
        }
        for r in rows
    ]


def get_cart_count(user_id: int) -> int:
    """Return the number of distinct product rows in the user's cart."""
    return Cart.objects.filter(user_id=user_id).count()
