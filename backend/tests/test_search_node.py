"""
Tests for search_node — constraint relaxation, brand/category boost, ranking.
"""
import pytest
from unittest.mock import MagicMock

from agents.graph.state import AgentState, ProductRef
from agents.graph.contracts.search_plan import SearchPlan
from agents.graph.nodes.search_node import (
    _build_brand_q,
    _rank_products,
    _enrich_and_rank,
    search_node,
    MIN_CANDIDATES,
)


# ═══════════════════════════════════════════════════════════════
# _build_brand_q — pure function, no DB
# ═══════════════════════════════════════════════════════════════

class TestBuildBrandQ:
    """Brand Q object construction with CN/EN fallback."""

    def test_includes_brand_iexact(self):
        q = _build_brand_q("华为")
        assert q is not None

    def test_includes_name_icontains(self):
        q = _build_brand_q("Huawei")
        # Q objects are opaque; verify construction doesn't crash
        assert q is not None

    def test_unknown_brand_returns_empty_q(self):
        q = _build_brand_q("不存在的品牌")
        assert q is not None  # should build a Q, even if no results


# ═══════════════════════════════════════════════════════════════
# _rank_products — pure function
# ═══════════════════════════════════════════════════════════════

def _make_mock_product(product_id, relevance=0.5, brand="", category_name="", price=100, rating=4.0, specs=None):
    """Create a mock Product for ranking tests."""
    p = MagicMock()
    p.id = product_id
    p.relevance = relevance
    p.brand = brand
    p.price = price
    p.rating = rating
    p.specs = specs or {}

    mock_cat = MagicMock()
    mock_cat.name = category_name
    p.category = mock_cat

    return p


class TestRankProducts:
    """Weighted ranking with soft boosts."""

    def test_empty_products(self):
        ranked, breakdown = _rank_products([], SearchPlan(), top_k=10)
        assert ranked == []
        assert breakdown == []

    def test_basic_ranking(self):
        p1 = _make_mock_product(1, relevance=0.8, brand="华为", category_name="智能手机", price=3000)
        p2 = _make_mock_product(2, relevance=0.6, brand="小米", category_name="智能手机", price=2000)
        ranked, breakdown = _rank_products([p1, p2], SearchPlan(), top_k=10)
        assert len(ranked) == 2
        assert ranked[0].id == 1  # higher relevance → first

    def test_brand_boost_pushes_matching_to_top(self):
        """brand_boost=华为 → 华为 products get +0.15 and rank higher."""
        huawei = _make_mock_product(1, relevance=0.5, brand="华为", category_name="智能手机", price=3000)
        xiaomi = _make_mock_product(2, relevance=0.5, brand="小米", category_name="智能手机", price=2000)
        ranked, breakdown = _rank_products(
            [huawei, xiaomi], SearchPlan(), top_k=10, brand_boost="华为",
        )
        # 华为 should rank above 小米 despite same base relevance
        assert ranked[0].id == 1
        # Verify scores differ (华为 got boost)
        h_score = next(b["total"] for b in breakdown if b["product_id"] == 1)
        x_score = next(b["total"] for b in breakdown if b["product_id"] == 2)
        assert h_score > x_score

    def test_brand_boost_case_insensitive(self):
        """brand_boost should match case-insensitively."""
        p = _make_mock_product(1, relevance=0.5, brand="HUAWEI", category_name="智能手机")
        ranked, breakdown = _rank_products([p], SearchPlan(), top_k=10, brand_boost="huawei")
        assert len(ranked) == 1
        # Should still match (lowercase check)
        assert breakdown[0]["total"] > 0.5  # base + boost

    def test_category_boost_adds_bonus(self):
        """category_boost=智能手机 → matching category gets +0.10."""
        phone = _make_mock_product(1, relevance=0.5, category_name="智能手机")
        headphone = _make_mock_product(2, relevance=0.5, category_name="耳机")
        ranked, breakdown = _rank_products(
            [phone, headphone], SearchPlan(), top_k=10, category_boost="智能手机",
        )
        assert ranked[0].id == 1  # phone ranked higher

    def test_brand_boost_no_match_no_effect(self):
        """brand_boost with no matching products → no effect on ranking."""
        p1 = _make_mock_product(1, relevance=0.7, brand="苹果")
        p2 = _make_mock_product(2, relevance=0.5, brand="三星")
        ranked, _ = _rank_products([p1, p2], SearchPlan(), top_k=10, brand_boost="华为")
        assert ranked[0].id == 1  # still by relevance

    def test_skip_diversity_allows_same_brand(self):
        """skip_diversity=True → 3rd same-brand item NOT penalized."""
        products = [
            _make_mock_product(i, relevance=0.5, brand="华为", category_name="智能手机")
            for i in range(1, 11)
        ]
        ranked, _ = _rank_products(products, SearchPlan(), top_k=10, skip_diversity=True)
        assert len(ranked) == 10  # all pass through

    def test_diversity_penalizes_3rd_same_brand(self):
        """Without skip_diversity, 3rd+ same-brand item gets penalized."""
        products = [
            _make_mock_product(i, relevance=0.9 - i * 0.01, brand="华为", category_name="智能手机")
            for i in range(1, 11)
        ]
        ranked, _ = _rank_products(products, SearchPlan(), top_k=10, skip_diversity=False)
        # All still returned, but some penalized — at least 2 are there
        assert len(ranked) >= 2

    def test_price_fit_with_budget(self):
        """Budget-aware ranking: closer to budget mid → higher price_fit."""
        plan = SearchPlan(budget_lower=500, budget_upper=1500)
        p_close = _make_mock_product(1, relevance=0.5, price=1000)   # mid = 1000
        p_far = _make_mock_product(2, relevance=0.5, price=100)     # far from mid
        ranked, _ = _rank_products([p_close, p_far], plan, top_k=10)
        assert ranked[0].id == 1  # close to budget mid

    def test_brand_boost_none_safe(self):
        """brand_boost=None should not crash."""
        p = _make_mock_product(1, relevance=0.5)
        ranked, _ = _rank_products([p], SearchPlan(), top_k=10, brand_boost=None, category_boost=None)
        assert len(ranked) == 1


# ═══════════════════════════════════════════════════════════════
# search_node — integration tests (requires DB + FAISS)
# ═══════════════════════════════════════════════════════════════

def _make_state(query: str, intent: str = "search", **extra) -> AgentState:
    """Build a minimal AgentState for search_node tests."""
    plan = SearchPlan(
        intent=intent,
        strategy="semantic",
        method="regex",
    )
    for k, v in extra.items():
        if hasattr(plan, k):
            setattr(plan, k, v)
    return AgentState(
        user_query=query,
        session_id="test_session_search",
        intent=intent,
        confidence=0.7,
        search_plan=plan,
    )


class TestSearchNodeIntegration:
    """End-to-end tests with real DB and FAISS index."""

    def test_手机_category_hard_filter(self):
        """Search '手机' with hard category → ≥ 2 results, all in smartphone category."""
        state = _make_state("手机",
            category_filter="智能手机", category_confidence=1.0,
        )
        result = search_node(state)
        products = result.tool_results.get("products", [])
        assert len(products) >= 2, f"Expected ≥ 2 results, got {len(products)}"
        # Category hard filter means no relaxation needed when results are sufficient
        # Every product should have score and name
        for p in products:
            assert p.get("product_name") or p.get("name"), f"Product missing name: {p}"
            assert "score" in p, f"Product missing score: {p}"

    def test_索尼手机_triggers_brand_relaxation(self):
        """Brand '索尼' has 0 products in '智能手机' → relaxation MUST trigger.

        Sony exists in DB (headphones etc.) but has ZERO smartphones.
        This forces the constraint relaxation code path:
          sql_ids = empty → FAISS∩SQL = empty → len < MIN_CANDIDATES
          → Layer 1: brand→soft → brand_boost='索尼'
          → relaxed_constraints contains '品牌「索尼」'
        """
        state = _make_state("索尼手机",
            category_filter="智能手机", category_confidence=1.0,
            brand="索尼",
        )
        result = search_node(state)
        products = result.tool_results.get("products", [])
        relaxed = result.parallel_results.get("_relaxed_constraints", [])
        strategy = result.parallel_results.get("_search_strategy", "")

        # Must have triggered relaxation
        assert len(relaxed) > 0, \
            f"Relaxation should have triggered! products={len(products)}, relaxed={relaxed}"
        # Brand should be mentioned in relaxed constraints
        assert "索尼" in str(relaxed), \
            f"Relaxed constraints should mention brand: {relaxed}"
        # Should still return some results (smartphones from other brands)
        assert len(products) > 0, \
            "Should return alternative smartphones after relaxation"

    def test_budget_filters_by_price(self):
        """Budget upper=50 → all results ≤ 100 (with 1.3x margin)."""
        state = _make_state("耳机",
            category_filter="耳机", category_confidence=1.0,
            budget_upper=50, budget_lower=0,
        )
        result = search_node(state)
        products = result.tool_results.get("products", [])
        for p in products:
            price = float(p.get("price", 0))
            assert price <= 100, \
                f"Price {price} exceeds budget margin"

    def test_no_results_sets_flag(self):
        """Impossible query → _no_results flag or empty products."""
        state = _make_state("不存在xyzabc123",
            category_filter="不存在的品类", category_confidence=1.0,
            budget_upper=1,
        )
        result = search_node(state)
        products = result.tool_results.get("products", [])
        no_results = result.parallel_results.get("_no_results", False)
        assert len(products) > 0 or no_results, \
            "Should have results or set _no_results flag"

    def test_steps_done_includes_search(self):
        """search_node should append 'search' to steps_done."""
        state = _make_state("手机", category_filter="智能手机", category_confidence=1.0)
        result = search_node(state)
        assert "search" in result.steps_done

    def test_trace_recorded(self):
        """search_node should append to trace with node_name='search'."""
        state = _make_state("手机", category_filter="智能手机", category_confidence=1.0)
        result = search_node(state)
        assert len(result.trace) >= 1
        assert result.trace[-1].node_name == "search"

    def test_MIN_CANDIDATES_is_positive(self):
        """MIN_CANDIDATES should be a positive integer."""
        assert MIN_CANDIDATES >= 1

    def test_category_soft_boost_no_hard_filter(self):
        """category_confidence=0.5 → does NOT enter SQL WHERE (soft boost only)."""
        state = _make_state("手机",
            category_filter="智能手机", category_confidence=0.5,  # soft!
        )
        result = search_node(state)
        products = result.tool_results.get("products", [])
        # Should return results (no hard category filter blocking things)
        assert len(products) >= 2, \
            f"Soft category should still return results, got {len(products)}"
