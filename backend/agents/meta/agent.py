"""MetaAgent — cross-agent analytics and weekly reporting."""
import logging
from agents.core.base_agent import BaseAgent, AgentContext, AgentResult

logger = logging.getLogger(__name__)

class MetaAgent(BaseAgent):
    agent_type = "meta"

    def _process(self, user_input: str, context: AgentContext) -> AgentResult:
        cmd = user_input.strip().lower()
        days = int(context.extra.get("days", 7)) if context.extra else 7

        if cmd in ("weekly", "report", "周报", "weekly_report"):
            return self._handle_weekly(days)
        else:
            return self._handle_weekly(7)

    def _handle_weekly(self, days: int) -> AgentResult:
        from agents.meta.analyzer import MetaAnalyzer
        analyzer = MetaAnalyzer()
        report = analyzer.generate_report(days=days)
        return AgentResult(
            status="ok",
            text=report["markdown"],
            data=report,
            tokens_used=0,
        )
