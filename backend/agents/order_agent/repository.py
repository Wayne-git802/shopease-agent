"""
Order Repository — data access layer for OrderAgent.

All DB operations go through here. No business logic, no validation.
Each write method accepts an idempotency_key for safe retry.
"""

from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional

from orders.models import Order, OrderStatus, Refund, RefundStatus


def _make_idempotency_key() -> str:
    return uuid.uuid4().hex[:12]


def _hash_snapshot(data: dict) -> str:
    """Deterministic hash of order state for snapshot comparison."""
    raw = "|".join(f"{k}={v}" for k, v in sorted(data.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════
# Read operations
# ═══════════════════════════════════════════════════════════

def get_user_orders(user_id: int, limit: int = 20) -> list[dict]:
    """Return user's orders, newest first."""
    orders = (
        Order.objects
        .filter(user_id=user_id, buyer_deleted=False)
        .order_by("-created_at")
    )[:limit]

    return [_order_to_dict(o) for o in orders]


def get_order_detail(user_id: int, order_id: int) -> dict | None:
    """Return single order detail if owned by user."""
    try:
        o = Order.objects.get(id=order_id, user_id=user_id)
        return _order_to_dict(o)
    except Order.DoesNotExist:
        return None


def get_logistics(user_id: int, order_id: int) -> dict:
    """Return shipping status. No tracking number in Phase 1 — use order status."""
    detail = get_order_detail(user_id, order_id)
    if not detail:
        return {"found": False, "error": "订单不存在"}

    status = detail["status"]
    status_map = {
        OrderStatus.PAID: ("paid", "订单已支付，等待发货"),
        OrderStatus.SHIPPED: ("shipped", "订单已发货，运输中"),
        OrderStatus.COMPLETED: ("completed", "订单已签收"),
        OrderStatus.CANCELLED: ("cancelled", "订单已取消"),
        OrderStatus.REFUNDED: ("refunded", "订单已退款"),
    }
    state, desc = status_map.get(status, ("unknown", "未知状态"))
    return {
        "found": True,
        "order_id": order_id,
        "order_no": detail["order_no"],
        "status": status,
        "state": state,
        "description": desc,
    }


# ═══════════════════════════════════════════════════════════
# Write operations (with idempotency)
# ═══════════════════════════════════════════════════════════

_IDEMPOTENT_CACHE: dict[str, dict] = {}  # key → cached result


def cancel_order(
    user_id: int, order_id: int, idempotency_key: str | None = None
) -> dict:
    """Cancel an order if allowed. Idempotent."""
    key = idempotency_key or _make_idempotency_key()

    if key in _IDEMPOTENT_CACHE:
        return _IDEMPOTENT_CACHE[key]

    try:
        o = Order.objects.get(id=order_id, user_id=user_id)
    except Order.DoesNotExist:
        return {"ok": False, "error": "订单不存在"}

    if o.is_final():
        return {"ok": False, "error": f"订单状态为 {o.status}，无法取消"}

    allowed, msg = o.can_transition_to(OrderStatus.CANCELLED, o.user)
    if not allowed:
        return {"ok": False, "error": msg}

    o.status = OrderStatus.CANCELLED
    o.save()

    result = {"ok": True, "order_no": o.order_no, "new_status": "cancelled"}
    _IDEMPOTENT_CACHE[key] = result
    return result


def create_refund(
    user_id: int, order_id: int, reason: str,
    idempotency_key: str | None = None,
) -> dict:
    """Create a refund request. Idempotent."""
    key = idempotency_key or _make_idempotency_key()

    if key in _IDEMPOTENT_CACHE:
        return _IDEMPOTENT_CACHE[key]

    try:
        o = Order.objects.get(id=order_id, user_id=user_id)
    except Order.DoesNotExist:
        return {"ok": False, "error": "订单不存在"}

    if o.is_final():
        return {"ok": False, "error": f"订单状态为 {o.status}，无法退款"}

    # Check if there's already a pending refund for this order
    existing = Refund.objects.filter(
        order=o, user_id=user_id, status=RefundStatus.PENDING
    ).first()
    if existing:
        return {
            "ok": True,
            "refund_id": existing.id,
            "refund_no": existing.refund_no,
            "status": existing.status,
            "note": "退款申请已存在",
        }

    refund = Refund.objects.create(
        refund_no=f"RF{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
        order=o,
        user_id=user_id,
        reason=reason or "用户申请退款",
        total_amount=o.total_amount,
        status=RefundStatus.PENDING,
    )

    result = {
        "ok": True,
        "refund_id": refund.id,
        "refund_no": refund.refund_no,
        "status": refund.status,
        "amount": str(o.total_amount),
    }
    _IDEMPOTENT_CACHE[key] = result
    return result


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _order_to_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "order_no": o.order_no,
        "status": o.status,
        "total_amount": str(o.total_amount),
        "address": o.address,
        "receiver_name": o.receiver_name,
        "receiver_phone": o.receiver_phone,
        "created_at": o.created_at.isoformat(),
        "is_final": o.is_final(),
    }


def get_order_snapshot(user_id: int, order_id: int) -> dict | None:
    """Get order state snapshot for confirmation hash."""
    detail = get_order_detail(user_id, order_id)
    if not detail:
        return None
    return {
        "order_id": detail["id"],
        "order_no": detail["order_no"],
        "status": detail["status"],
        "is_final": detail["is_final"],
        "amount": detail["total_amount"],
    }
