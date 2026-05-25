"""Repository layer — centralized data access for all agents.

All database queries live here.  No agent or tool module touches
Django ORM directly.  This keeps SQL in one place so schema changes
don't cascade across the codebase.

Naming convention:
    find_*   → query, returns list/dict or None
    save_*   → create/update
    count_*  → aggregate
    delete_* → delete

Every method degrades gracefully: returns empty list/None/0 on error,
never raises.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import Q, Count, Avg, Sum

logger = logging.getLogger(__name__)

User = get_user_model()


# ═══════════════════════════════════════════════════════════════
# Products
# ═══════════════════════════════════════════════════════════════

def find_products(query: str, limit: int = 5) -> list[dict]:
    """Search products by name/description.  Returns list of dicts."""
    try:
        from products.models import Product
        q = query.strip()
        if not q:
            return []
        products = Product.objects.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        ).select_related('category')[:limit]

        return [{
            'id': p.id, 'name': p.name,
            'price': str(p.price),
            'category': p.category.name if p.category else '',
            'stock': getattr(p, 'stock_quantity', '未知'),
            'rating': round(p.reviews.aggregate(avg=Avg('rating')).get('avg') or 0, 1),
            'image_url': getattr(p, 'image', '') or '',
        } for p in products]
    except Exception as exc:
        logger.warning("find_products failed: %s", exc)
        return []


def find_low_stock_products(threshold: int = 10, limit: int = 20) -> list[dict]:
    """Find products with inventory at or below threshold."""
    try:
        from products.models import Inventory
        low = Inventory.objects.filter(
            quantity__lte=threshold
        ).select_related('product')[:limit]
        return [{
            'product_id': inv.product.id,
            'name': inv.product.name,
            'current_stock': inv.quantity,
            'severity': 'critical' if inv.quantity == 0 else 'warning',
        } for inv in low]
    except Exception as exc:
        logger.warning("find_low_stock_products failed: %s", exc)
        return []


def find_categories() -> list[dict]:
    """List all active top-level categories."""
    try:
        from products.models import Category
        cats = Category.objects.filter(is_active=True, parent__isnull=True)
        return [{'id': c.id, 'name': c.name, 'slug': c.slug} for c in cats]
    except Exception as exc:
        logger.warning("find_categories failed: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════
# Orders
# ═══════════════════════════════════════════════════════════════

def find_order(order_id: str, user_id: int) -> Optional[dict]:
    """Look up a specific order.  Returns None if not found/unauthorized."""
    try:
        from orders.models import Order
        order = Order.objects.get(id=order_id, user_id=user_id)
    except Exception:
        return None

    status_map = {
        'paid': '已付款', 'shipped': '运输中',
        'completed': '已送达', 'cancelled': '已取消', 'refunded': '已退款',
    }
    items = [{
        'product_name': item.product.name if item.product else '未知',
        'quantity': item.quantity, 'price': str(item.price),
    } for item in order.items.all()]

    return {
        'order_id': order_id,
        'status': status_map.get(order.status, order.status),
        'total_amount': str(order.total_amount),
        'items': items,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M'),
    }


def find_user_orders(user_id: int, limit: int = 5) -> list[dict]:
    """List recent orders for a user."""
    try:
        from orders.models import Order
        status_map = {'paid': '已付款', 'shipped': '运输中',
                      'completed': '已送达', 'cancelled': '已取消', 'refunded': '已退款'}
        orders = Order.objects.filter(user_id=user_id).order_by('-created_at')[:limit]
        return [{
            'order_id': o.id,
            'status': status_map.get(o.status, o.status),
            'total_amount': str(o.total_amount),
            'item_count': o.items.count(),
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M'),
        } for o in orders]
    except Exception as exc:
        logger.warning("find_user_orders failed: %s", exc)
        return []


def find_stale_unpaid_orders(hours: int = 24, limit: int = 20) -> list[dict]:
    """Find orders unpaid for more than N hours."""
    try:
        from orders.models import Order
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        orders = Order.objects.filter(
            status='paid', created_at__lt=cutoff
        ).select_related('user')[:limit]

        now = datetime.now(timezone.utc)
        return [{
            'order_id': o.id, 'user_id': o.user_id,
            'hours_unpaid': round((now - o.created_at).total_seconds() / 3600, 1),
            'amount': str(o.total_amount),
            'severity': 'warning' if (now - o.created_at).total_seconds() < 72 * 3600 else 'critical',
        } for o in orders]
    except Exception as exc:
        logger.warning("find_stale_unpaid_orders failed: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════
# Agent Persistence
# ═══════════════════════════════════════════════════════════════

def save_agent_logs(entries: list[dict]) -> int:
    """Bulk-create AgentLog entries.  Returns count saved."""
    try:
        from agents.models import AgentLog
        objs = [AgentLog(**e) for e in entries]
        AgentLog.objects.bulk_create(objs)
        return len(objs)
    except Exception as exc:
        logger.warning("save_agent_logs failed: %s", exc)
        return 0


def get_agent_stats(hours: int = 24, agent_type: Optional[str] = None) -> dict:
    """Get AgentLog statistics for the recent window.

    Returns {total, errors, error_pct, avg_latency_ms, slow_count, by_agent}.
    """
    try:
        from agents.models import AgentLog
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        qs = AgentLog.objects.filter(created_at__gte=cutoff)
        if agent_type:
            qs = qs.filter(agent_type=agent_type)

        total = qs.count()
        errors = qs.filter(status='failed').count()
        error_pct = round(errors / total * 100, 1) if total else 0
        avg_lat = qs.filter(latency_ms__gt=0).aggregate(avg=Avg('latency_ms'))['avg'] or 0
        slow = qs.filter(latency_ms__gte=5000).count()

        by_agent = list(
            qs.values('agent_type').annotate(
                t=Count('id'), f=Count('id', filter=Q(status='failed'))
            ).values_list('agent_type', 't', 'f')
        )
        return {
            'total': total, 'errors': errors,
            'error_pct': error_pct,
            'avg_latency_ms': round(avg_lat, 0),
            'slow_count': slow,
            'by_agent': [{'agent': a, 'total': t, 'failed': f,
                          'pct': round(f/t*100,1) if t else 0} for a, t, f in by_agent],
        }
    except Exception as exc:
        logger.warning("get_agent_stats failed: %s", exc)
        return {'total': 0, 'errors': 0, 'error_pct': 0,
                'avg_latency_ms': 0, 'slow_count': 0, 'by_agent': []}


def save_conversation(user_id: int, session_id: str, agent_type: str,
                      role: str, content: str, tokens_used: int = 0) -> bool:
    """Save a conversation turn."""
    try:
        from agents.models import AgentConversation
        AgentConversation.objects.create(
            user_id=user_id, session_id=session_id,
            agent_type=agent_type, role=role,
            content=content, tokens_used=tokens_used,
        )
        return True
    except Exception as exc:
        logger.warning("save_conversation failed: %s", exc)
        return False


def count_conversation_rounds(user_id: int, session_id: str) -> int:
    """Count user messages in a session."""
    try:
        from agents.models import AgentConversation
        return AgentConversation.objects.filter(
            user_id=user_id, session_id=session_id, role='user',
        ).count()
    except Exception:
        return 0


def get_recent_conversation(user_id: int, session_id: str,
                            limit: int = 12) -> list[str]:
    """Get recent messages in a session for summarization."""
    try:
        from agents.models import AgentConversation
        msgs = AgentConversation.objects.filter(
            user_id=user_id, session_id=session_id,
        ).order_by('-created_at')[:limit]
        return [m.content for m in msgs if m.role == 'user']
    except Exception:
        return []


def get_conversation_history(user_id: int, session_id: str = '',
                             agent_type: str = 'customer_service',
                             limit: int = 50) -> list[dict]:
    """Get conversation history."""
    try:
        from agents.models import AgentConversation
        qs = AgentConversation.objects.filter(
            user_id=user_id, agent_type=agent_type,
        )
        if session_id:
            qs = qs.filter(session_id=session_id)
        qs = qs.order_by('-created_at')[:limit]
        return [{
            'id': m.id, 'role': m.role, 'content': m.content,
            'created_at': m.created_at,
        } for m in qs]
    except Exception as exc:
        logger.warning("get_conversation_history failed: %s", exc)
        return []


# ── UserPreferences ────────────────────────────────────────────

def get_user_preferences(user_id: int) -> dict[str, str]:
    """Get all preferences for a user."""
    try:
        from agents.models import UserPreference
        prefs = {}
        for up in UserPreference.objects.filter(user_id=user_id):
            prefs[up.key] = up.value
        return prefs
    except Exception:
        return {}


def save_user_preference(user_id: int, key: str, value: str,
                         source_agent: str = '', confidence: float = 1.0) -> bool:
    """Upsert a user preference."""
    try:
        from agents.models import UserPreference
        UserPreference.objects.update_or_create(
            user_id=user_id, key=key,
            defaults={'value': value, 'source_agent': source_agent,
                      'confidence': confidence},
        )
        return True
    except Exception as exc:
        logger.warning("save_user_preference failed: %s", exc)
        return False


# ── Alerts ─────────────────────────────────────────────────────

def save_alert(title: str, description: str, severity: str,
               source: str = 'ops') -> Optional[int]:
    """Create an AgentAlert.  Returns alert id."""
    try:
        from agents.models import AgentAlert
        alert = AgentAlert.objects.create(
            title=title, description=description,
            severity=severity, source=source,
        )
        return alert.id
    except Exception as exc:
        logger.warning("save_alert failed: %s", exc)
        return None


def find_alerts(severity: Optional[str] = None, resolved: Optional[bool] = None,
                limit: int = 50) -> list[dict]:
    """Query alerts."""
    try:
        from agents.models import AgentAlert
        qs = AgentAlert.objects.all()
        if severity:
            qs = qs.filter(severity=severity)
        if resolved is not None:
            qs = qs.filter(resolved=resolved)
        qs = qs.order_by('-created_at')[:limit]
        return [{
            'id': a.id, 'title': a.title, 'description': a.description,
            'severity': a.severity, 'source': a.source,
            'resolved': a.resolved, 'created_at': a.created_at.isoformat(),
        } for a in qs]
    except Exception as exc:
        logger.warning("find_alerts failed: %s", exc)
        return []


def resolve_alert_by_id(alert_id: int) -> bool:
    """Mark an alert resolved."""
    try:
        from agents.models import AgentAlert
        return AgentAlert.objects.filter(id=alert_id).update(resolved=True) > 0
    except Exception as exc:
        logger.warning("resolve_alert_by_id failed: %s", exc)
        return False


def get_alerts_in_window(hours: int = 24) -> list[dict]:
    """Get alerts from the last N hours (for digest)."""
    try:
        from agents.models import AgentAlert
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        alerts = AgentAlert.objects.filter(created_at__gte=cutoff)
        criticals = alerts.filter(severity='critical').order_by('-created_at')[:5]
        warnings = alerts.filter(severity='warning').order_by('-created_at')[:3]
        return {
            'total': alerts.count(),
            'critical_count': alerts.filter(severity='critical').count(),
            'warning_count': alerts.filter(severity='warning').count(),
            'info_count': alerts.filter(severity='info').count(),
            'top_critical': [a.title for a in criticals],
            'top_warnings': [a.title for a in warnings],
        }
    except Exception as exc:
        logger.warning("get_alerts_in_window failed: %s", exc)
        return {'total': 0, 'critical_count': 0, 'warning_count': 0,
                'info_count': 0, 'top_critical': [], 'top_warnings': []}


# ── SemanticCache ──────────────────────────────────────────────

def find_cached_responses(agent_type: str) -> list[dict]:
    """Get all cache entries for an agent type (for similarity search)."""
    try:
        from agents.models import SemanticCache
        return [{
            'id': e.id, 'query_embedding': e.query_embedding,
            'query_text': e.query_text, 'response_text': e.response_text,
        } for e in SemanticCache.objects.filter(agent_type=agent_type).iterator()]
    except Exception as exc:
        logger.warning("find_cached_responses failed: %s", exc)
        return []


def save_cache_entry(query_text: str, response_text: str,
                     query_embedding: bytes, agent_type: str) -> bool:
    """Store a semantic cache entry."""
    try:
        from agents.models import SemanticCache
        SemanticCache.objects.create(
            query_text=query_text, response_text=response_text,
            query_embedding=query_embedding, agent_type=agent_type,
        )
        return True
    except Exception as exc:
        logger.warning("save_cache_entry failed: %s", exc)
        return False


def clear_cache(agent_type: Optional[str] = None) -> int:
    """Clear semantic cache.  Returns count deleted."""
    try:
        from agents.models import SemanticCache
        qs = SemanticCache.objects.all()
        if agent_type:
            qs = qs.filter(agent_type=agent_type)
        count, _ = qs.delete()
        return count
    except Exception as exc:
        logger.warning("clear_cache failed: %s", exc)
        return 0


# ── Users ──────────────────────────────────────────────────────

def get_user_name(user_id: int) -> str:
    """Get a user's display name."""
    try:
        user = User.objects.get(id=user_id)
        return getattr(user, 'username', '') or getattr(user, 'name', '') or ''
    except Exception:
        return ''


# ── DB Health ──────────────────────────────────────────────────

def check_db_connection() -> dict:
    """Basic connectivity + row counts.  Returns health dict."""
    try:
        from django.db import connections
        db_conn = connections['default']
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            tables = {}
            for tbl in ['products_product', 'orders_order', 'users_user',
                        'agent_logs', 'agent_alerts']:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                    tables[tbl] = cursor.fetchone()[0]
                except Exception:
                    tables[tbl] = -1

        severity = 'info'
        if tables.get('products_product', 0) == 0:
            severity = 'critical'

        return {'connected': True, 'severity': severity, 'tables': tables}
    except Exception as exc:
        return {'connected': False, 'severity': 'critical', 'tables': {}, 'error': str(exc)}
