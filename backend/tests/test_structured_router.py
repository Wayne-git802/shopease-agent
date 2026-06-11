"""
Tests for StructuredRouter.detect() — pure keyword-based intent detection.

All tests are pure-function tests: no Django, no DB, no LLM.
"""

import pytest

from agents.graph.structured_router import (
    StructuredRouter,
    StructuredIntent,
    StructuredResult,
)


# ── Shared router instance ──

@pytest.fixture
def router() -> StructuredRouter:
    return StructuredRouter()


# ── Positive: structured intents ─────────────────────────────────────────

class TestDetectStructured:
    """Queries that should be detected as structured intents."""

    def test_order_tracking(self, router: StructuredRouter):
        """'我的订单在哪' → ORDER."""
        assert router.detect("我的订单在哪") == StructuredIntent.ORDER

    def test_cart_lookup(self, router: StructuredRouter):
        """'看看购物车' → CART."""
        assert router.detect("看看购物车") == StructuredIntent.CART

    def test_purchase_history(self, router: StructuredRouter):
        """'我之前买过什么' → PURCHASE_HISTORY."""
        assert router.detect("我之前买过什么") == StructuredIntent.PURCHASE_HISTORY


# ── Negative: not structured ─────────────────────────────────────────────

class TestDetectNone:
    """Queries that should NOT be detected as structured intents."""

    def test_greeting(self, router: StructuredRouter):
        """'你好' → NONE (greeting, not structured)."""
        assert router.detect("你好") == StructuredIntent.NONE

    def test_product_question(self, router: StructuredRouter):
        """'上次买的耳机怎么样' → NONE (product query, not structured)."""
        assert router.detect("上次买的耳机怎么样") == StructuredIntent.NONE

    def test_recommend_request(self, router: StructuredRouter):
        """'帮我推荐耳机' → NONE (search/recommend, not structured)."""
        assert router.detect("帮我推荐耳机") == StructuredIntent.NONE


# ── Edge cases ───────────────────────────────────────────────────────────

class TestDetectEdgeCases:
    """Boundary and edge-case behaviour."""

    def test_empty_query(self, router: StructuredRouter):
        """Empty query → NONE."""
        assert router.detect("") == StructuredIntent.NONE

    def test_all_order_keywords(self, router: StructuredRouter):
        """Every ORDER keyword triggers ORDER."""
        from agents.graph.structured_router import _ORDER_KEYWORDS
        for kw in _ORDER_KEYWORDS:
            assert router.detect(f"{kw} 看看") == StructuredIntent.ORDER, (
                f"Keyword '{kw}' should trigger ORDER"
            )

    def test_all_cart_keywords(self, router: StructuredRouter):
        """Every CART keyword triggers CART."""
        from agents.graph.structured_router import _CART_KEYWORDS
        for kw in _CART_KEYWORDS:
            assert router.detect(kw) == StructuredIntent.CART, (
                f"Keyword '{kw}' should trigger CART"
            )

    def test_all_purchase_history_keywords(self, router: StructuredRouter):
        """Every PURCHASE_HISTORY keyword triggers PURCHASE_HISTORY."""
        from agents.graph.structured_router import _PURCHASE_HISTORY_KEYWORDS
        for kw in _PURCHASE_HISTORY_KEYWORDS:
            assert router.detect(f"请问{kw}") == StructuredIntent.PURCHASE_HISTORY, (
                f"Keyword '{kw}' should trigger PURCHASE_HISTORY"
            )

    def test_priority_order_over_cart_for_recommend(self, router: StructuredRouter):
        """'帮我推荐耳机' should not match any — verify NONE (keyword absence)."""
        # This query has no structured keywords; ensure it stays NONE
        assert router.detect("帮我推荐耳机") == StructuredIntent.NONE

    def test_cart_english_keyword(self, router: StructuredRouter):
        """'my cart please' → CART (English 'cart' keyword)."""
        assert router.detect("my cart please") == StructuredIntent.CART
