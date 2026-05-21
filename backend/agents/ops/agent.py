"""OpsAgent — automated operations monitoring and alerting.

Capabilities:
  - Health check: run all monitors, create alerts, return summary
  - List alerts: query recent alerts by severity
  - Daily report: generate a formatted operations digest
  - Resolve alerts: mark alerts as handled

Integration:
  - Uses monitors.py for data collection (no LLM needed for basic checks)
  - Uses alerts.py for alert storage, routing, and push
  - Inherits BaseAgent for unified logging
"""

import logging
from typing import Optional

from agents.core.base_agent import BaseAgent, AgentContext, AgentResult

logger = logging.getLogger(__name__)


class OpsAgent(BaseAgent):
    """Automated operations agent for ShopEase."""

    agent_type = 'ops'

    # ── main logic ──────────────────────────────────────────────

    def _process(self, user_input: str, context: AgentContext) -> AgentResult:
        """Route the request to the appropriate handler.

        Recognized commands:
            health / 健康检查 → run monitors + create alerts
            alerts / 告警列表 → query recent alerts
            report / 日报    → generate daily digest
            resolve:<id>     → mark alert as resolved
        """
        cmd = user_input.strip().lower()

        if cmd in ('health', '健康检查', 'check'):
            return self._handle_health()
        elif cmd in ('alerts', '告警', '告警列表', 'list'):
            return self._handle_alerts(context.extra.get('severity'))
        elif cmd in ('report', '日报', 'digest'):
            return self._handle_report()
        elif cmd.startswith('resolve:'):
            alert_id_str = cmd.split(':', 1)[1].strip()
            return self._handle_resolve(alert_id_str)
        else:
            return self._handle_health()  # default

    # ── handlers ────────────────────────────────────────────────

    def _handle_health(self) -> AgentResult:
        """Run all monitors, create alerts for findings, return summary."""
        from .monitors import run_all_checks, get_health_summary
        from .alerts import process_findings

        # Run monitors
        findings = run_all_checks()

        # Create alerts from findings
        alert_ids = process_findings(findings)

        # Generate summary
        summary = get_health_summary()

        # Count severities
        criticals = len([f for f in findings if f.get('severity') == 'critical'])
        warnings = len([f for f in findings if f.get('severity') == 'warning'])

        text_lines = [
            f"系统状态: {summary['status']}",
            f"🔴 严重: {criticals} 条",
            f"🟡 警告: {warnings} 条",
            f"📋 检查项: {summary['total_findings']} 项",
        ]

        # Add specific findings
        for f in findings:
            if f.get('severity') in ('critical', 'warning'):
                ftype = f.get('type', '')
                if ftype == 'db_health':
                    text_lines.append(
                        f"  {'❌' if not f.get('connected') else '✅'} 数据库: "
                        f"{'连接正常' if f.get('connected') else '连接失败'}"
                    )
                elif ftype == 'error_rate':
                    text_lines.append(
                        f"  ⚠️ Agent 错误率: {f.get('error_pct',0)}% "
                        f"({f.get('error_count',0)}/{f.get('total_requests',0)})"
                    )
                elif ftype == 'slow_responses':
                    text_lines.append(
                        f"  🐌 平均延迟: {f.get('avg_latency_ms',0)}ms"
                    )

        return AgentResult(
            status=summary['status'] if summary['status'] != 'unhealthy' else 'degraded',
            text='\n'.join(text_lines),
            data=summary,
            tokens_used=0,
        )

    def _handle_alerts(self, severity: Optional[str] = None) -> AgentResult:
        """Query recent alerts."""
        from .alerts import get_alerts

        alerts = get_alerts(severity=severity, resolved=False, limit=20)

        if not alerts:
            return AgentResult(status='ok', text='✅ 最近无未解决告警', data={'alerts': []})

        criticals = [a for a in alerts if a['severity'] == 'critical']
        warnings = [a for a in alerts if a['severity'] == 'warning']

        lines = [
            f"📋 未解决告警: {len(alerts)} 条",
            f"  🔴 严重: {len(criticals)} 条",
            f"  🟡 警告: {len(warnings)} 条",
            "",
        ]
        for a in alerts[:10]:
            emoji = '🔴' if a['severity'] == 'critical' else '🟡' if a['severity'] == 'warning' else '🟢'
            lines.append(f"  {emoji} #{a['id']} {a['title']}")

        return AgentResult(
            status='degraded' if criticals else 'ok',
            text='\n'.join(lines),
            data={'alerts': alerts, 'total': len(alerts)},
            tokens_used=0,
        )

    def _handle_report(self) -> AgentResult:
        """Generate a daily operations digest."""
        from .alerts import generate_daily_digest

        digest = generate_daily_digest()
        return AgentResult(
            status='ok',
            text=digest,
            data={'digest': digest},
            tokens_used=0,
        )

    def _handle_resolve(self, alert_id_str: str) -> AgentResult:
        """Mark an alert as resolved."""
        from .alerts import resolve_alert

        try:
            alert_id = int(alert_id_str)
        except ValueError:
            return AgentResult(
                status='failed',
                error=f'无效的告警 ID: {alert_id_str}',
            )

        ok = resolve_alert(alert_id)
        if ok:
            return AgentResult(
                status='ok',
                text=f'✅ 告警 #{alert_id} 已标记为已解决',
            )
        else:
            return AgentResult(
                status='degraded',
                text=f'⚠️ 告警 #{alert_id} 解决失败（可能不存在）',
            )
