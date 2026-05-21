"""Ops monitors — detect anomalies in the ShopEase platform.

Each monitor returns a list of findings (dicts) that the OpsAgent
can process, alert on, or include in reports.

Monitors:
  - unpaid_orders: long-pending unpaid orders
  - low_stock: products below reorder threshold
  - error_rate: recent AgentLog error spike
  - slow_responses: AgentLog latency spike
  - db_health: basic DB connectivity + table row counts
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from django.db import connections
from django.db.models import Count, Avg, Q

logger = logging.getLogger(__name__)


# ── Configuration ───────────────────────────────────────────────

# Orders unpaid for more than N hours → alert
UNPAID_ORDER_HOURS = 24

# Inventory below this threshold → alert
LOW_STOCK_THRESHOLD = 10

# Error rate above this % → alert
ERROR_RATE_THRESHOLD = 10.0  # percent

# Latency above this ms → alert
SLOW_LATENCY_THRESHOLD_MS = 5000

# Lookback window for stats
LOOKBACK_HOURS = 24


# ── Monitor functions ───────────────────────────────────────────

def check_unpaid_orders() -> list[dict]:
    """Find orders that have been unpaid for too long.

    Returns list of {order_id, user_id, hours_unpaid, amount}.
    """
    try:
        from orders.models import Order
    except ImportError:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=UNPAID_ORDER_HOURS)
    try:
        orders = Order.objects.filter(
            status='paid',           # paid but not shipped/completed
            created_at__lt=cutoff,
        ).select_related('user')[:20]

        findings = []
        for o in orders:
            hours = (datetime.now(timezone.utc) - o.created_at).total_seconds() / 3600
            findings.append({
                'type': 'unpaid_order',
                'severity': 'warning' if hours < 72 else 'critical',
                'order_id': o.id,
                'user_id': o.user_id,
                'hours_unpaid': round(hours, 1),
                'amount': str(o.total_amount),
            })
        return findings
    except Exception as exc:
        logger.warning("check_unpaid_orders failed: %s", exc)
        return []


def check_low_stock() -> list[dict]:
    """Find products with critically low inventory.

    Returns list of {product_id, name, current_stock, shop_id}.
    """
    try:
        from products.models import Product, Inventory
    except ImportError:
        return []

    try:
        low = Inventory.objects.filter(
            quantity__lte=LOW_STOCK_THRESHOLD
        ).select_related('product')[:20]

        findings = []
        for inv in low:
            product = inv.product
            severity = 'critical' if inv.quantity == 0 else 'warning'
            findings.append({
                'type': 'low_stock',
                'severity': severity,
                'product_id': product.id,
                'name': product.name,
                'current_stock': inv.quantity,
                'shop_id': getattr(product, 'shop_id', None),
            })
        return findings
    except Exception as exc:
        logger.warning("check_low_stock failed: %s", exc)
        return []


def check_error_rate() -> Optional[dict]:
    """Check AgentLog error rate in the recent window.

    Returns a stats dict or None if no data.
    """
    try:
        from agents.models import AgentLog
    except ImportError:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    try:
        total = AgentLog.objects.filter(created_at__gte=cutoff).count()
        if total == 0:
            return None

        errors = AgentLog.objects.filter(
            created_at__gte=cutoff,
            status='failed',
        ).count()

        error_pct = round(errors / total * 100, 1)

        # Per-agent breakdown
        agent_rows = list(
            AgentLog.objects
            .filter(created_at__gte=cutoff)
            .values('agent_type')
            .annotate(
                total=Count('id'),
                failed=Count('id', filter=Q(status='failed')),
            )
            .values_list('agent_type', 'total', 'failed')
        )

        return {
            'type': 'error_rate',
            'severity': 'critical' if error_pct > ERROR_RATE_THRESHOLD else 'info',
            'total_requests': total,
            'error_count': errors,
            'error_pct': error_pct,
            'window_hours': LOOKBACK_HOURS,
            'by_agent': [
                {'agent': agent, 'total': t, 'failed': f, 'pct': round(f/t*100,1) if t else 0}
                for agent, t, f in by_agent
            ],
        }
    except Exception as exc:
        logger.warning("check_error_rate failed: %s", exc)
        return None


def check_slow_responses() -> Optional[dict]:
    """Check for slow Agent responses in the recent window.

    Returns a stats dict or None if no data.
    """
    try:
        from agents.models import AgentLog
    except ImportError:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    try:
        stats = AgentLog.objects.filter(
            created_at__gte=cutoff,
            latency_ms__gt=0,  # exclude untracked
        ).aggregate(
            avg_latency=Avg('latency_ms'),
            total=Count('id'),
        )

        total = stats['total'] or 0
        if total == 0:
            return None

        avg_latency = round(stats['avg_latency'] or 0, 0)

        slow_count = AgentLog.objects.filter(
            created_at__gte=cutoff,
            latency_ms__gte=SLOW_LATENCY_THRESHOLD_MS,
        ).count()

        return {
            'type': 'slow_responses',
            'severity': 'warning' if avg_latency > SLOW_LATENCY_THRESHOLD_MS else 'info',
            'avg_latency_ms': avg_latency,
            'slow_count': slow_count,
            'total_requests': total,
            'threshold_ms': SLOW_LATENCY_THRESHOLD_MS,
            'window_hours': LOOKBACK_HOURS,
        }
    except Exception as exc:
        logger.warning("check_slow_responses failed: %s", exc)
        return None


def check_db_health() -> dict:
    """Basic database connectivity and row counts.

    Returns a health dict.
    """
    health = {
        'type': 'db_health',
        'severity': 'info',
        'connected': False,
        'tables': {},
    }

    try:
        db_conn = connections['default']
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            health['connected'] = True

            # Key table row counts
            for table in ['products_product', 'orders_order', 'users_user',
                          'agent_logs', 'agent_alerts']:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    health['tables'][table] = cursor.fetchone()[0]
                except Exception:
                    health['tables'][table] = -1  # table missing

        # If any core table is empty, that's a warning
        for table in ['products_product', 'users_user']:
            if health['tables'].get(table, 0) == 0:
                health['severity'] = 'critical'
                break

    except Exception as exc:
        health['error'] = str(exc)
        health['severity'] = 'critical'

    return health


# ── Aggregate ───────────────────────────────────────────────────

def run_all_checks() -> list[dict]:
    """Run all monitors and return all findings.

    Each finding is a dict with at least: type, severity.
    """
    findings = []

    # Per-item findings (list of dicts)
    findings.extend(check_unpaid_orders())
    findings.extend(check_low_stock())

    # Summary findings (single dict or None)
    for check in [check_error_rate, check_slow_responses]:
        result = check()
        if result:
            findings.append(result)

    # DB health is always included
    findings.append(check_db_health())

    return findings


def get_health_summary() -> dict:
    """Quick health check summary for the /health/ endpoint."""
    findings = run_all_checks()

    criticals = [f for f in findings if f.get('severity') == 'critical']
    warnings = [f for f in findings if f.get('severity') == 'warning']

    if criticals:
        status = 'unhealthy'
    elif warnings:
        status = 'degraded'
    else:
        status = 'healthy'

    return {
        'status': status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'critical_count': len(criticals),
        'warning_count': len(warnings),
        'total_findings': len(findings),
        'findings': findings,
    }
