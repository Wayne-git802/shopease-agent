"""
StructuredRouter — keyword-based structured query detection and direct SQL execution.

Routes order/cart/purchase_history intents to Django ORM queries,
bypassing the FAISS + RRF search graph entirely.

Usage:
    from .structured_router import StructuredRouter, StructuredIntent

    sr = StructuredRouter()
    intent = sr.detect("我的订单在哪", user_id=1)
    if intent != StructuredIntent.NONE:
        result = sr.execute(intent, user_id=1)
        print(result.reply)
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════

class StructuredIntent(Enum):
    ORDER = "order"
    CART = "cart"
    PURCHASE_HISTORY = "purchase_history"
    NONE = "none"


@dataclass
class StructuredResult:
    intent: StructuredIntent
    data: dict
    reply: str


# ═══════════════════════════════════════════════════════════════
# Keyword sets — rule-based detection, no LLM
# ═══════════════════════════════════════════════════════════════

_ORDER_KEYWORDS: list[str] = [
    "我的订单", "订单在哪", "订单状态", "查订单",
    "物流", "发货", "到哪了",
]

_CART_KEYWORDS: list[str] = [
    "购物车", "我的购物车", "购物车里", "加了什么", "cart",
]

_PURCHASE_HISTORY_KEYWORDS: list[str] = [
    "我买过", "买了什么", "购买记录", "历史订单", "之前买的", "买过什么",
]

# ── Status display ──

_STATUS_LABELS: dict[str, str] = {
    "paid": "已付款",
    "shipped": "已发货",
    "completed": "已完成",
    "cancelled": "已取消",
    "refunded": "已退款",
}


# ═══════════════════════════════════════════════════════════════
# StructuredRouter
# ═══════════════════════════════════════════════════════════════

class StructuredRouter:
    """Detect structured queries via keyword matching and execute direct SQL.

    Detection is pure (no DB, no LLM).  Execution uses Django ORM.
    """

    # ── Detection ─────────────────────────────────────────────

    def detect(self, query: str, user_id: int | None = None) -> StructuredIntent:
        """Match keywords + rules to classify structured intent.  No LLM.

        Returns StructuredIntent.NONE when no keyword matches — caller
        should fall through to the normal L0/L1 routing pipeline.
        """
        if not query:
            return StructuredIntent.NONE

        # Lowercase for English keywords (e.g. "cart"); Chinese is unaffected
        q = query.strip().lower()

        # Order keywords
        for kw in _ORDER_KEYWORDS:
            if kw in q:
                return StructuredIntent.ORDER

        # Cart keywords
        for kw in _CART_KEYWORDS:
            if kw in q:
                return StructuredIntent.CART

        # Purchase history keywords
        for kw in _PURCHASE_HISTORY_KEYWORDS:
            if kw in q:
                return StructuredIntent.PURCHASE_HISTORY

        return StructuredIntent.NONE

    # ── Execution ─────────────────────────────────────────────

    def execute(self, intent: StructuredIntent, user_id: int,
                session_id: str = "") -> StructuredResult:
        """Run the appropriate Django ORM query and build a natural reply."""
        import django
        django.setup()

        if intent == StructuredIntent.ORDER:
            return self._query_orders(user_id)
        elif intent == StructuredIntent.CART:
            return self._query_cart(user_id)
        elif intent == StructuredIntent.PURCHASE_HISTORY:
            return self._query_purchase_history(user_id)
        else:
            return StructuredResult(
                intent=StructuredIntent.NONE,
                data={},
                reply="抱歉，无法处理该请求。",
            )

    # ── Private: per-intent queries ───────────────────────────

    def _query_orders(self, user_id: int) -> StructuredResult:
        """SELECT id, order_no, status, total_amount, created_at
        FROM orders WHERE user_id=xxx ORDER BY created_at DESC LIMIT 5."""
        from orders.models import Order

        orders = (
            Order.objects
            .filter(user_id=user_id)
            .order_by("-created_at")[:5]
        )

        if not orders:
            return StructuredResult(
                intent=StructuredIntent.ORDER,
                data={"items": []},
                reply="您还没有订单记录，快去逛逛吧！",
            )

        items: list[dict] = []
        for o in orders:
            items.append({
                "order_no": o.order_no,
                "status": o.status,
                "status_label": _STATUS_LABELS.get(o.status, o.status),
                "total_amount": float(o.total_amount),
                "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
            })

        # Natural Chinese reply
        lines = [f"您最近的 {len(orders)} 笔订单："]
        for i, item in enumerate(items, 1):
            lines.append(
                f"{i}. 订单 {item['order_no']} — "
                f"¥{item['total_amount']:.2f} — "
                f"{item['status_label']} "
                f"({item['created_at']})"
            )

        return StructuredResult(
            intent=StructuredIntent.ORDER,
            data={"items": items},
            reply="\n".join(lines),
        )

    def _query_cart(self, user_id: int) -> StructuredResult:
        """SELECT cart items with product info for user."""
        from orders.models import Cart

        cart_items = (
            Cart.objects
            .filter(user_id=user_id)
            .select_related("product")
        )

        if not cart_items:
            return StructuredResult(
                intent=StructuredIntent.CART,
                data={"items": []},
                reply="您的购物车是空的，快去添加心仪的商品吧！",
            )

        items: list[dict] = []
        total = 0.0
        for c in cart_items:
            price = float(c.product.price)
            subtotal = price * c.quantity
            total += subtotal
            items.append({
                "product_id": c.product.id,
                "product_name": c.product.name,
                "price": price,
                "quantity": c.quantity,
                "subtotal": subtotal,
            })

        lines = [f"您的购物车中有 {len(items)} 件商品："]
        for i, item in enumerate(items, 1):
            lines.append(
                f"{i}. {item['product_name']} × {item['quantity']} — "
                f"¥{item['subtotal']:.2f}"
            )
        lines.append(f"合计：¥{total:.2f}")

        return StructuredResult(
            intent=StructuredIntent.CART,
            data={"items": items},
            reply="\n".join(lines),
        )

    def _query_purchase_history(self, user_id: int) -> StructuredResult:
        """Same query as orders but with product-level detail and
        a different reply template for purchase-history intent."""
        from orders.models import Order

        orders = (
            Order.objects
            .filter(user_id=user_id)
            .order_by("-created_at")[:5]
        )

        if not orders:
            return StructuredResult(
                intent=StructuredIntent.PURCHASE_HISTORY,
                data={"items": []},
                reply="您还没有购买记录，快去挑选喜欢的商品吧！",
            )

        items: list[dict] = []
        for o in orders:
            # Fetch product names via order items
            order_items = o.items.select_related("product")[:3]
            product_names = [oi.product.name for oi in order_items]

            items.append({
                "order_no": o.order_no,
                "products": product_names,
                "total_amount": float(o.total_amount),
                "status": o.status,
                "status_label": _STATUS_LABELS.get(o.status, o.status),
                "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
            })

        lines = [f"您最近购买过 {len(orders)} 笔订单的商品："]
        for i, item in enumerate(items, 1):
            products_str = "、".join(item["products"]) if item["products"] else "—"
            lines.append(
                f"{i}. {products_str} — "
                f"¥{item['total_amount']:.2f} — "
                f"{item['created_at']}"
            )

        return StructuredResult(
            intent=StructuredIntent.PURCHASE_HISTORY,
            data={"items": items},
            reply="\n".join(lines),
        )
