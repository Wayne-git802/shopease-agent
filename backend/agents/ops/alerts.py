"""Ops alert routing — store, route, and digest alerts.

Alert routing rules (from ARCHITECTURE.md):
CRITICAL -> instant push via messaging gateway (WeChat/Feishu)
                   + store in MySQL + dashboard red badge
    🟡 WARNING  → store in MySQL + dashboard display
                   + daily WeChat digest summary
    🟢 INFO     → store in MySQL only (no push)

Integration:
    The gateway push is done via a callback mechanism:
    - `set_push_callback(fn)` registers a function that takes an alert dict
      and pushes it to the messaging channel.
    - In the Django app, this callback can use the gateway's REST API or
      a shared channel.
    - Without a callback, alerts are stored in DB only (safe fallback).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from django.db.models import Count, Q

logger = logging.getLogger(__name__)

# Callback for external notification push (set by app startup)
_push_callback: Optional[Callable[[dict], None]] = None


def set_push_callback(callback: Callable[[dict], None]) -> None:
    """Register a function that pushes alerts to messaging platforms.

    The callback receives an alert dict with keys:
        title, description, severity, source, created_at
    """
    global _push_callback
    _push_callback = callback


# ── Alert creation ──────────────────────────────────────────────

def create_alert(title: str, description: str, severity: str,
                 source: str = 'ops') -> Optional[int]:
    """Create an alert and route it by severity.

    Args:
        title:       short summary (e.g. "订单 ORD-001 超时未支付")
        description: detailed info
        severity:    'critical' | 'warning' | 'info'
        source:      which monitor generated this

    Returns:
        The alert's DB id, or None if DB write failed.
    """
    # Validate severity
    valid = {'critical', 'warning', 'info'}
    severity = severity if severity in valid else 'info'

    alert_id = None

    # ── Store to MySQL ──
    try:
        from agents.models import AgentAlert
        alert = AgentAlert.objects.create(
            title=title,
            description=description,
            severity=severity,
            source=source,
        )
        alert_id = alert.id
        logger.info("[%s] Alert #%d: %s", severity.upper(), alert_id, title)
    except Exception as exc:
        logger.warning("Failed to store alert: %s", exc)
        # Continue anyway — try to push even if DB fails

    # ── Route by severity ──
    alert_data = {
        'id': alert_id,
        'title': title,
        'description': description,
        'severity': severity,
        'source': source,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    if severity == 'critical':
        _push_alert(alert_data)
    # warning + info: stored in DB, no immediate push
    # (warning goes into daily digest)

    return alert_id


# ── Batch alerting from monitor findings ────────────────────────

def process_findings(findings: list[dict]) -> list[int]:
    """Create alerts from a batch of monitor findings.

    Args:
        findings: list of dicts from monitors (must have type, severity)

    Returns:
        List of created alert IDs.
    """
    ids = []
    for f in findings:
        ftype = f.get('type', 'unknown')
        severity = f.get('severity', 'info')

        # Build a human-readable title and description
        if ftype == 'unpaid_order':
            title = f"订单 {f.get('order_id','?')} 超时未支付"
            description = (
                f"订单 {f.get('order_id','?')} 已下单 {f.get('hours_unpaid',0)} 小时"
                f"仍未支付，金额 ¥{f.get('amount','0')}"
            )
        elif ftype == 'low_stock':
            title = f"商品 {f.get('name','?')} 库存不足"
            description = (
                f"商品 {f.get('name','?')} (ID:{f.get('product_id','?')}) "
                f"当前库存 {f.get('current_stock',0)}"
            )
        elif ftype == 'error_rate':
            pct = f.get('error_pct', 0)
            title = f"Agent 错误率 {pct}%"
            description = (
                f"过去 {f.get('window_hours',24)} 小时内 "
                f"{f.get('error_count',0)}/{f.get('total_requests',0)} 请求失败"
            )
        elif ftype == 'slow_responses':
            title = f"Agent 响应延迟 {f.get('avg_latency_ms',0)}ms"
            description = (
                f"平均延迟 {f.get('avg_latency_ms',0)}ms, "
                f"{f.get('slow_count',0)} 次超 {f.get('threshold_ms',0)}ms 阈值"
            )
        elif ftype == 'db_health':
            if not f.get('connected'):
                title = "数据库连接失败"
                description = f"无法连接 MySQL: {f.get('error','unknown')}"
            else:
                title = "数据库健康检查"
                description = (
                    f"连接正常, 表行数: {f.get('tables',{})}"
                )
        else:
            title = f"未知异常: {ftype}"
            description = str(f)

        alert_id = create_alert(title, description, severity, source=ftype)
        if alert_id:
            ids.append(alert_id)

    return ids


# ── Push ────────────────────────────────────────────────────────

def _push_alert(alert: dict) -> bool:
    """Push an alert through the registered callback.

    Returns True if pushed, False if no callback or push failed.
    """
    if _push_callback is None:
        logger.debug("No push callback registered. Alert %s not pushed.",
                     alert.get('id'))
        return False

    try:
        _push_callback(alert)
        return True
    except Exception as exc:
        logger.warning("Push callback failed for alert %s: %s",
                       alert.get('id'), exc)
        return False


# ── Query ───────────────────────────────────────────────────────

def get_alerts(severity: Optional[str] = None,
               resolved: Optional[bool] = None,
               limit: int = 50) -> list[dict]:
    """Query alerts from the database.

    Args:
        severity: filter by 'critical', 'warning', 'info', or None=all
        resolved: filter by resolved status, or None=all
        limit:    max results

    Returns:
        List of alert dicts.
    """
    try:
        from agents.models import AgentAlert
        qs = AgentAlert.objects.all()
        if severity:
            qs = qs.filter(severity=severity)
        if resolved is not None:
            qs = qs.filter(resolved=resolved)
        qs = qs.order_by('-created_at')[:limit]

        return [{
            'id': a.id,
            'title': a.title,
            'description': a.description,
            'severity': a.severity,
            'source': a.source,
            'resolved': a.resolved,
            'created_at': a.created_at.isoformat(),
        } for a in qs]
    except Exception as exc:
        logger.warning("get_alerts failed: %s", exc)
        return []


def resolve_alert(alert_id: int) -> bool:
    """Mark an alert as resolved."""
    try:
        from agents.models import AgentAlert
        updated = AgentAlert.objects.filter(id=alert_id).update(resolved=True)
        return updated > 0
    except Exception as exc:
        logger.warning("resolve_alert(%d) failed: %s", alert_id, exc)
        return False


# ── Digest ──────────────────────────────────────────────────────

def generate_daily_digest() -> str:
    """Generate a daily alert digest for WeChat push.

    Summarizes the last 24 hours of alerts, grouped by severity.
    Returns markdown-formatted text.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        from agents.models import AgentAlert
        alerts = AgentAlert.objects.filter(created_at__gte=cutoff)

        total = alerts.count()
        criticals = alerts.filter(severity='critical').count()
        warnings = alerts.filter(severity='warning').count()
        infos = alerts.filter(severity='info').count()

        lines = [
            "📊 **ShopEase 运维日报**",
            f"_{datetime.now().strftime('%Y-%m-%d')}_",
            "",
        ]

        if total == 0:
            lines.append("✅ 过去 24 小时无告警")
        else:
            lines.append(f"🔴 严重: {criticals} 条")
            lines.append(f"🟡 警告: {warnings} 条")
            lines.append(f"🟢 信息: {infos} 条")
            lines.append(f"📋 合计: {total} 条")
            lines.append("")

            # Show top criticals
            top_crit = alerts.filter(severity='critical').order_by('-created_at')[:5]
            if top_crit:
                lines.append("**⚠️ 严重告警:**")
                for a in top_crit:
                    lines.append(f"  • {a.title}")
                lines.append("")

            # Show recent warnings
            top_warn = alerts.filter(severity='warning').order_by('-created_at')[:3]
            if top_warn:
                lines.append("**⚡ 警告:**")
                for a in top_warn:
                    lines.append(f"  • {a.title}")

        return '\n'.join(lines)

    except Exception as exc:
        logger.warning("generate_daily_digest failed: %s", exc)
        return "⚠️ 运维日报生成失败"
