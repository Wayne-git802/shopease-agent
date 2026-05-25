"""MetaAnalyzer — weekly statistics from agent logs. Pure SQL, no LLM."""
import logging
from datetime import datetime, timedelta, timezone
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone as tz

logger = logging.getLogger(__name__)

class MetaAnalyzer:
    """Aggregate agent logs into a weekly report."""

    def generate_report(self, days: int = 7) -> dict:
        """Generate a weekly operations report. Returns dict with markdown text."""
        try:
            from agents.models import AgentLog, AgentConversation, AgentAlert
        except Exception:
            return self._empty_report("Database not available")

        since = tz.now() - timedelta(days=days)

        # ── overall stats ──
        logs = AgentLog.objects.filter(created_at__gte=since)
        total = logs.count()
        if total == 0:
            return self._empty_report("No agent activity in this period")

        ok_count = logs.filter(status="ok").count()
        failed_count = logs.filter(status="failed").count()
        success_rate = round(ok_count / total * 100, 1) if total else 0
        avg_latency = round(logs.aggregate(avg=Avg("latency_ms"))["avg"] or 0)
        total_tokens = logs.aggregate(s=Sum("tokens_used"))["s"] or 0
        cache_hits = logs.filter(cache_hit=True).count()
        cache_rate = round(cache_hits / total * 100, 1) if total else 0

        # ── per-agent breakdown ──
        agent_rows = []
        for atype in ["customer_service", "ops", "recommend"]:
            qs = logs.filter(agent_type=atype)
            cnt = qs.count()
            if cnt == 0:
                continue
            ok = qs.filter(status="ok").count()
            fail = qs.filter(status="failed").count()
            lat = round(qs.aggregate(avg=Avg("latency_ms"))["avg"] or 0)
            tok = qs.aggregate(s=Sum("tokens_used"))["s"] or 0
            agent_rows.append(f"| {atype} | {cnt} | {ok} | {fail} | {lat}ms | {tok:,} |")

        # ── conversations ──
        convs = AgentConversation.objects.filter(created_at__gte=since)
        conv_total = convs.count()
        unique_users = convs.values("user").distinct().count()
        unique_sessions = convs.values("session_id").distinct().count()

        # ── alerts ──
        alerts = AgentAlert.objects.filter(created_at__gte=since)
        alert_total = alerts.count()
        criticals = alerts.filter(severity="critical", resolved=False).count()
        warnings = alerts.filter(severity="warning", resolved=False).count()
        unresolved = alerts.filter(resolved=False).count()

        # ── build markdown ──
        date_from = since.strftime("%Y-%m-%d")
        date_to = tz.now().strftime("%Y-%m-%d")

        lines = [
            f"# ShopEase 周度运营报告 ({date_from} ~ {date_to})",
            "",
            "## 📊 总体概览",
            f"- 总请求: {total:,} 次 | 成功率: {success_rate}% | 平均延迟: {avg_latency}ms",
            f"- 总 Token 消耗: {total_tokens:,} | 缓存命中率: {cache_rate}%",
            f"- 活跃用户: {unique_users} 人 | 会话数: {unique_sessions}",
            "",
            "## 🤖 各 Agent 表现",
            "| Agent | 请求数 | 成功 | 失败 | 平均延迟 | Token |",
            "|-------|--------|------|------|---------|-------|",
        ]
        lines.extend(agent_rows)
        lines += [
            "",
            "## 🚨 告警",
            f"- 总告警: {alert_total} 条 | 🔴 严重: {criticals} 条 | 🟡 警告: {warnings} 条",
            f"- 未解决: {unresolved} 条",
        ]

        markdown = "\n".join(lines)

        return {
            "markdown": markdown,
            "stats": {
                "total_requests": total,
                "success_rate": success_rate,
                "avg_latency_ms": avg_latency,
                "total_tokens": total_tokens,
                "cache_hit_rate": cache_rate,
                "unique_users": unique_users,
                "unique_sessions": unique_sessions,
                "agents": [],
                "alerts": {"total": alert_total, "critical": criticals, "warning": warnings, "unresolved": unresolved},
            },
            "date_from": date_from,
            "date_to": date_to,
        }

    def _empty_report(self, reason: str) -> dict:
        now = tz.now()
        return {
            "markdown": f"# ShopEase 周度运营报告\n\n_{reason}_",
            "stats": {},
            "date_from": (now - timedelta(days=7)).strftime("%Y-%m-%d"),
            "date_to": now.strftime("%Y-%m-%d"),
        }
