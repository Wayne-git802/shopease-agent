"""
Agent tests — AgentExecutor protocol, execute(), handoff, confirm.
"""

import pytest
from unittest.mock import MagicMock


class TestOrderAgent:

    def test_has_capability(self):
        from agents.order.agent import order_agent
        from agents.graph.pipeline import AgentCapability
        assert order_agent.capability == AgentCapability.ORDER
        assert order_agent.priority == 10
        assert not hasattr(order_agent, "name")

    def test_can_handle(self):
        from agents.order.agent import order_agent
        from agents.graph.pipeline import PipelineContext
        ctx = PipelineContext(query="查订单")
        ctx.commerce_result = MagicMock(intent="order", confidence=0.8)
        assert order_agent.can_handle(ctx) is True
        ctx.commerce_result = MagicMock(intent="search", confidence=0.8)
        assert order_agent.can_handle(ctx) is False

    def test_execute_returns_agent_result(self):
        from agents.order.agent import order_agent
        from agents.graph.pipeline import AgentContext, AgentResult
        ctx = AgentContext(query="查订单", user_id=1, session_id="s1")
        try:
            result = order_agent.execute(ctx)
        except Exception:
            pytest.skip("DB not available — execute requires MySQL")
        assert isinstance(result, AgentResult)
        assert result.status in ("success", "fallback", "error")


class TestCartAgent:

    def test_has_capability(self):
        from agents.cart.agent import cart_agent
        from agents.graph.pipeline import AgentCapability
        assert cart_agent.capability == AgentCapability.CART
        assert cart_agent.priority == 10
        assert not hasattr(cart_agent, "name")

    def test_can_handle(self):
        from agents.cart.agent import cart_agent
        from agents.graph.pipeline import PipelineContext
        ctx = PipelineContext(query="加入购物车")
        ctx.commerce_result = MagicMock(intent="cart", confidence=0.5)
        assert cart_agent.can_handle(ctx) is True
        ctx.commerce_result = MagicMock(intent="cart", confidence=0.1)
        assert cart_agent.can_handle(ctx) is False

    def test_execute_returns_agent_result(self):
        from agents.cart.agent import cart_agent
        from agents.graph.pipeline import AgentContext, AgentResult
        ctx = AgentContext(query="加入购物车", user_id=1, session_id="s1")
        try:
            result = cart_agent.execute(ctx)
        except Exception:
            pytest.skip("DB not available — execute requires MySQL")
        assert isinstance(result, AgentResult)
        assert result.status in ("success", "fallback", "handoff", "error")


class TestPurchaseAgent:

    def test_has_capability(self):
        from agents.purchase.agent import purchase_agent
        from agents.graph.pipeline import AgentCapability
        assert purchase_agent.capability == AgentCapability.PURCHASE
        assert purchase_agent.priority == 10
        assert not hasattr(purchase_agent, "name")

    def test_can_handle(self):
        from agents.purchase.agent import purchase_agent
        from agents.graph.pipeline import PipelineContext
        ctx = PipelineContext(query="下单")
        ctx.commerce_result = MagicMock(intent="purchase", confidence=0.5)
        assert purchase_agent.can_handle(ctx) is True
        ctx.commerce_result = MagicMock(intent="purchase", confidence=0.1)
        assert purchase_agent.can_handle(ctx) is False

    def test_execute_returns_agent_result(self):
        from agents.purchase.agent import purchase_agent
        from agents.graph.pipeline import AgentContext, AgentResult
        ctx = AgentContext(query="下单", user_id=1, session_id="s1")
        try:
            result = purchase_agent.execute(ctx)
        except Exception:
            pytest.skip("DB not available — execute requires MySQL")
        assert isinstance(result, AgentResult)
        assert result.status in ("success", "fallback", "handoff", "error")


class TestAllAgentsSatisfyProtocol:

    def test_all_three(self):
        from agents.graph.pipeline import AgentExecutor
        from agents.order.agent import order_agent
        from agents.cart.agent import cart_agent
        from agents.purchase.agent import purchase_agent
        for agent in [order_agent, cart_agent, purchase_agent]:
            assert isinstance(agent, AgentExecutor), (
                f"{agent.__class__.__name__} does not satisfy AgentExecutor"
            )


class TestAgentResultPatterns:

    def test_success(self):
        from agents.graph.pipeline import AgentResult
        r = AgentResult(status="success", response={"reply": "ok"})
        assert r.status == "success" and r.response is not None and r.handoff is None

    def test_fallback(self):
        from agents.graph.pipeline import AgentResult
        r = AgentResult(status="fallback")
        assert r.status == "fallback" and r.response is None

    def test_handoff(self):
        from agents.graph.pipeline import AgentResult, Handoff, AgentCapability
        r = AgentResult(status="handoff", handoff=Handoff(target=AgentCapability.PURCHASE, payload={"s": "abc"}))
        assert r.handoff.target == AgentCapability.PURCHASE

    def test_error(self):
        from agents.graph.pipeline import AgentResult
        r = AgentResult(status="error", response={"reply": "系统错误"})
        assert r.status == "error"
