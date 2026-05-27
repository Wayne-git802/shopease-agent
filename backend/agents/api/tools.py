"""Tool functions for the CustomerServiceAgent.

Each tool represents a capability the agent can use to help customers.
Tools return structured results that the LLM can format into natural responses.
"""

from typing import Optional

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q, Avg
from products.models import Product, Category

User = get_user_model()


def search_products(query: str, limit: int = 5) -> list[dict]:
    """Search products by name or description.

    Args:
        query:  search keywords
        limit:  max results

    Returns:
        List of product dicts: {id, name, price, category, stock, rating}
    """
    if not query or not query.strip():
        return []

    q = query.strip()
    products = Product.objects.filter(
        Q(name__icontains=q) | Q(description__icontains=q)
    ).select_related('category')[:limit]

    results = []
    for p in products:
        # Compute average rating
        rating_qs = p.reviews.aggregate(avg=Avg('rating')) if hasattr(p, 'reviews') else {}
        avg_rating = round(rating_qs.get('avg') or 0, 1)

        results.append({
            'id': p.id,
            'name': p.name,
            'price': str(p.price),
            'category': p.category.name if p.category else '',
            'stock': getattr(p, 'stock_quantity', '未知'),
            'rating': avg_rating,
            'image_url': getattr(p, 'image', '') or '',
        })
    return results


def get_order_status(order_id: str, user_id: int) -> Optional[dict]:
    """Look up a specific order for a user.

    Args:
        order_id:  order number (e.g. 'ORD-20240521-0001')
        user_id:   the authenticated user's ID

    Returns:
        Order dict or None if not found / not authorized.
    """
    try:
        from orders.models import Order
    except ImportError:
        return None

    try:
        order = Order.objects.get(id=order_id, user_id=user_id)
    except Order.DoesNotExist:
        return None

    # Map status to Chinese display
    status_map = {
        'paid': '已付款',
        'shipped': '运输中',
        'completed': '已送达',
        'cancelled': '已取消',
        'refunded': '已退款',
    }

    items = []
    for item in order.items.all():
        items.append({
            'product_name': item.product.name if item.product else '未知商品',
            'quantity': item.quantity,
            'price': str(item.price),
        })

    return {
        'order_id': order_id,
        'status': status_map.get(order.status, order.status),
        'status_raw': order.status,
        'total_amount': str(order.total_amount),
        'items': items,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
        'shipping_address': getattr(order, 'shipping_address', '') or '',
    }


def get_user_orders(user_id: int, limit: int = 5) -> list[dict]:
    """List recent orders for a user.

    Args:
        user_id:  the authenticated user's ID
        limit:    max results

    Returns:
        List of order dicts (simplified).
    """
    try:
        from orders.models import Order
    except ImportError:
        return []

    orders = Order.objects.filter(user_id=user_id).order_by('-created_at')[:limit]

    status_map = {
        'paid': '已付款', 'shipped': '运输中',
        'completed': '已送达', 'cancelled': '已取消', 'refunded': '已退款',
    }

    return [{
        'order_id': o.id,
        'status': status_map.get(o.status, o.status),
        'total_amount': str(o.total_amount),
        'item_count': o.items.count(),
        'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
    } for o in orders]


def get_return_policy() -> str:
    """Return the store's return/refund policy."""
    return (
        "退货政策：\n"
        "1. 7 天无理由退货（收货后 7 天内，商品完好）\n"
        "2. 质量问题：包邮退货，全额退款\n"
        "3. 非质量问题：买家承担退货运费\n"
        "4. 退款到账：支付宝/微信 1-3 个工作日\n"
        "5. 特殊商品（食品、内衣等）不支持无理由退货\n"
        "如需退货，请在订单详情页点击「申请退货」按钮"
    )


def get_product_categories() -> list[dict]:
    """List all active product categories."""
    cats = Category.objects.filter(is_active=True, parent__isnull=True)
    return [{'id': c.id, 'name': c.name, 'slug': c.slug} for c in cats]
