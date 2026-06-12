"""
Tests for reference_resolver — ordinal extraction + action detection.
Pure functions, no DB, no session.
"""
import pytest
from agents.graph.routing.reference_resolver import (
    resolve_reference,
    ReferenceContext,
    ProductReference,
    ReferenceAction,
    ClarificationReason,
)


def _ctx(*products):
    """Build ReferenceContext from (product_id, product_name) tuples."""
    return ReferenceContext(
        products=[ProductReference(product_id=pid, product_name=name) for pid, name in products],
        last_query="手机",
    )


class TestResolveReference:
    """Port of _self_test cases + edge cases."""

    # ── Positive: action + ordinal ──

    def test_buy_second(self):
        """'买第二个' → PURCHASE, product_ids=[102]"""
        ctx = _ctx((101, "华为FreeBuds 6i"), (102, "小米Buds 5 Pro"))
        r = resolve_reference("买第二个", ctx)
        assert r.action == ReferenceAction.PURCHASE
        assert r.target.product_ids == [102]
        assert r.capability == "purchase"
        assert r.source_index == 2
        assert not r.requires_clarification

    def test_ordinal_only_defaults_to_view_detail(self):
        """Bare '第二个' → VIEW_DETAIL (not clarification)."""
        ctx = _ctx((101, "华为FreeBuds 6i"), (102, "小米Buds 5 Pro"))
        r = resolve_reference("第二个", ctx)
        assert r.action == ReferenceAction.VIEW_DETAIL
        assert r.target.product_ids == [102]
        assert r.capability == "search"
        assert r.clarification_reason is None
        assert not r.requires_clarification

    def test_index_out_of_range_clarifies(self):
        """'第十五个' with 2 products → PRODUCT_NOT_FOUND clarification."""
        ctx = _ctx((101, "华为FreeBuds 6i"), (102, "小米Buds 5 Pro"))
        r = resolve_reference("第十五个", ctx)
        assert r.clarification_reason == ClarificationReason.PRODUCT_NOT_FOUND
        assert r.target.product_ids == []
        assert r.capability is None
        assert r.requires_clarification

    def test_add_to_cart_first(self):
        """'加购物车第一个' → ADD_TO_CART, product_ids=[101]."""
        ctx = _ctx((101, "华为FreeBuds 6i"), (102, "小米Buds 5 Pro"))
        r = resolve_reference("加购物车第一个", ctx)
        assert r.action == ReferenceAction.ADD_TO_CART
        assert r.target.product_ids == [101]
        assert r.capability == "cart"
        assert r.source_index == 1
        assert not r.requires_clarification

    def test_no_reference_returns_empty(self):
        """'推荐手机' → no reference detected."""
        ctx = _ctx((101, "华为FreeBuds 6i"), (102, "小米Buds 5 Pro"))
        r = resolve_reference("推荐手机", ctx)
        assert r.target.product_ids == []
        assert r.action is None
        assert r.capability is None
        assert not r.requires_clarification

    def test_view_detail_second(self):
        """'看看第二个' → VIEW_DETAIL."""
        ctx = _ctx((101, "华为FreeBuds 6i"), (102, "小米Buds 5 Pro"))
        r = resolve_reference("看看第二个", ctx)
        assert r.action == ReferenceAction.VIEW_DETAIL
        assert r.target.product_ids == [102]
        assert r.capability == "search"

    def test_empty_context_clarifies(self):
        """'第一个' with empty context → PRODUCT_NOT_FOUND."""
        r = resolve_reference("第一个", ReferenceContext())
        assert r.action is None
        assert r.target.product_ids == []
        assert r.capability is None
        assert r.clarification_reason == ClarificationReason.PRODUCT_NOT_FOUND

    # ── Edge cases ──

    def test_chinese_digit_two(self):
        """'第二个' → index 1 (0-based)."""
        ctx = _ctx((101, "A"), (102, "B"))
        r = resolve_reference("第二个", ctx)
        assert r.source_index == 2

    def test_action_without_ordinal(self):
        """'我要购买' without ordinal → no reference (no ordinal match)."""
        ctx = _ctx((101, "A"), (102, "B"))
        r = resolve_reference("我要购买", ctx)
        assert r.target.product_ids == []
        assert r.action is None

    def test_empty_query(self):
        ctx = _ctx((101, "A"))
        r = resolve_reference("", ctx)
        assert r.target.product_ids == []

    def test_purchase_action_before_ordinal(self):
        """'买第一个' → PURCHASE, product_ids=[101]."""
        ctx = _ctx((101, "A"), (102, "B"))
        r = resolve_reference("买第一个", ctx)
        assert r.action == ReferenceAction.PURCHASE
        assert r.target.product_ids == [101]
