"""RecommendAgent — product recommendation engine wrapper."""
import logging
from typing import Optional
from agents.core.base_agent import BaseAgent, AgentContext, AgentResult

logger = logging.getLogger(__name__)


class RecommendAgent(BaseAgent):
    agent_type = "recommend"

    def _process(self, user_input: str, context: AgentContext) -> AgentResult:
        cmd = user_input.strip().lower()
        if cmd == "popular":
            return self._handle_popular(context.extra.get("limit", 10))
        elif cmd == "similar":
            return self._handle_similar(int(context.extra.get("product_id", 0)), context.extra.get("limit", 5))
        elif cmd == "for-you":
            return self._handle_for_you(context.user_id, context.extra.get("limit", 10))
        elif cmd == "trending":
            return self._handle_trending(context.extra.get("limit", 10))
        else:
            return self._handle_popular(10)

    def _handle_popular(self, limit: int) -> AgentResult:
        from agents.commerce.engine import RecommendEngine
        engine = RecommendEngine()
        products = engine.get_popular(limit=limit)
        return AgentResult(status="ok", text=f"Found {len(products)} popular products", data={"products": products}, tokens_used=0)

    def _handle_similar(self, product_id: int, limit: int) -> AgentResult:
        from agents.commerce.engine import RecommendEngine
        engine = RecommendEngine()
        products = engine.get_similar(product_id, limit=limit)
        return AgentResult(status="ok", text=f"Found {len(products)} similar products", data={"products": products}, tokens_used=0)

    def _handle_for_you(self, user_id: Optional[int], limit: int) -> AgentResult:
        from agents.commerce.engine import RecommendEngine
        engine = RecommendEngine()
        products = engine.get_for_user(user_id or 0, limit=limit)
        return AgentResult(status="ok", text=f"Found {len(products)} recommendations for you", data={"products": products}, tokens_used=0)

    def _handle_trending(self, limit: int) -> AgentResult:
        from agents.commerce.engine import RecommendEngine
        engine = RecommendEngine()
        products = engine.get_trending(limit=limit)
        return AgentResult(status="ok", text=f"Found {len(products)} trending products", data={"products": products}, tokens_used=0)
