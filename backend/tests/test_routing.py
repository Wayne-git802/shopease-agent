"""
Routing tests — affinity, classifier, grounding gate.
"""

import pytest
from unittest.mock import MagicMock


class TestAffinityTable:

    def test_all_values_are_agent_capabilities(self):
        from agents.graph.routing.affinity import _AFFINITY_TABLE
        from agents.graph.pipeline import AgentCapability
        expected = {
            "order_created_card": AgentCapability.ORDER,
            "confirm_dialog": AgentCapability.PURCHASE,
            "cart_card": AgentCapability.CART,
        }
        assert _AFFINITY_TABLE == expected

    def test_build_action_context_empty(self):
        from agents.graph.routing.affinity import build_action_context
        ctx = build_action_context("")
        assert ctx.active_blocks == []

    def test_route_by_affinity_no_blocks(self):
        from agents.graph.routing.affinity import route_by_affinity, ConversationActionContext
        ctx = ConversationActionContext(active_blocks=[])
        assert route_by_affinity(ctx, "hello") is None

    def test_route_by_affinity_strong_intent_breaks(self):
        from agents.graph.routing.affinity import route_by_affinity, ConversationActionContext, ActionBlock
        ctx = ConversationActionContext(active_blocks=[ActionBlock(type="cart_card", data={})])
        assert route_by_affinity(ctx, "退款") is None  # strong intent keyword

    def test_route_by_affinity_returns_capability(self):
        from agents.graph.routing.affinity import route_by_affinity, ConversationActionContext, ActionBlock
        from agents.graph.pipeline import AgentCapability
        ctx = ConversationActionContext(active_blocks=[ActionBlock(type="cart_card", data={})])
        # Use a query with no strong intent keywords
        result = route_by_affinity(ctx, "")
        assert result == AgentCapability.CART


class TestClassifier:

    def test_classify_importable(self):
        from agents.graph.routing.classifier import classify, apply_signals
        assert callable(classify) and callable(apply_signals)

    def test_signal_delta_keys(self):
        from agents.graph.routing.classifier import _SIGNAL_DELTA
        assert set(_SIGNAL_DELTA.keys()) == {"capability", "stop", "ack", "negative_feedback"}

    def test_threshold_in_range(self):
        from agents.graph.routing.classifier import _COMMERCE_CONFIDENCE_THRESHOLD
        assert 0.0 <= _COMMERCE_CONFIDENCE_THRESHOLD <= 1.0


class TestGroundingGate:

    def test_check_importable(self):
        from agents.graph.routing.grounding_gate import check
        assert callable(check)

    def test_skips_non_search_intent(self):
        from agents.graph.routing.grounding_gate import check
        from agents.graph.pipeline import PipelineContext
        ctx = PipelineContext(query="hello")
        ctx.commerce_result = MagicMock(intent="chat", confidence=0.5)
        assert check(ctx) is None

    def test_skips_no_commerce_result(self):
        from agents.graph.routing.grounding_gate import check
        from agents.graph.pipeline import PipelineContext
        ctx = PipelineContext(query="hello")
        ctx.commerce_result = None
        assert check(ctx) is None


class TestRoutingInit:

    def test_classify_importable(self):
        from agents.graph.routing import classify
        assert callable(classify)


class TestHasStrongIntent:

    def test_importable(self):
        from agents.graph.state_router import has_strong_intent
        assert callable(has_strong_intent)

    def test_old_name_gone(self):
        import agents.graph.state_router as sr
        assert not hasattr(sr, "_has_strong_intent")
