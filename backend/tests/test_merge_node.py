"""
Tests for merge_node pure functions: _normalize_group, _normalize_per_type,
_fuse, _rerank_mmr, _resolve_merge_policy.

All functions are pure (no side effects beyond Candidate.score mutation
in normalization) and testable in isolation.
"""

import pytest

from agents.graph.nodes.merge_node import (
    Candidate,
    _normalize_group,
    _normalize_per_type,
    _fuse,
    _rerank_mmr,
    _resolve_merge_policy,
)


# ── Helpers ─────────────────────────────────────────────────────────────

def make_candidate(
    id_: int,
    score: float = 0.5,
    score_type: str = "semantic",
    source: str = "search",
    score_confidence: float = 1.0,
    category: str = "",
) -> Candidate:
    """Factory for Candidate dataclass."""
    return Candidate(
        id=id_,
        score=score,
        score_type=score_type,
        source=source,
        score_confidence=score_confidence,
        category=category,
    )


# ── _normalize_group ────────────────────────────────────────────────────

class TestNormalizeGroup:
    """Min-max normalize scores within a group (mutates in-place)."""

    def test_basic_normalization(self):
        """Scores [1, 2, 3] → [0.0, 0.5, 1.0]."""
        candidates = [
            make_candidate(1, score=1.0),
            make_candidate(2, score=2.0),
            make_candidate(3, score=3.0),
        ]
        result = _normalize_group(candidates)
        assert len(result) == 3
        assert result[0].score == 0.0
        assert result[1].score == 0.5
        assert result[2].score == 1.0

    def test_all_same_scores(self):
        """All scores equal → all become 0.5."""
        candidates = [
            make_candidate(1, score=5.0),
            make_candidate(2, score=5.0),
            make_candidate(3, score=5.0),
        ]
        result = _normalize_group(candidates)
        assert all(c.score == 0.5 for c in result)

    def test_single_item(self):
        """Single item → normalized to 0.5 (hi == lo)."""
        candidates = [make_candidate(1, score=42.0)]
        result = _normalize_group(candidates)
        assert result[0].score == 0.5

    def test_empty_list(self):
        """Empty list → returned as-is."""
        assert _normalize_group([]) == []

    def test_negative_scores(self):
        """Scores with negative values normalize correctly."""
        candidates = [
            make_candidate(1, score=-5.0),
            make_candidate(2, score=5.0),
        ]
        result = _normalize_group(candidates)
        assert result[0].score == 0.0
        assert result[1].score == 1.0

    def test_preserves_other_fields(self):
        """Non-score fields are not modified."""
        candidates = [
            make_candidate(1, score=1.0, source="search", category="books"),
            make_candidate(2, score=3.0, source="recommend", category="electronics"),
        ]
        result = _normalize_group(candidates)
        assert result[0].source == "search"
        assert result[0].category == "books"
        assert result[1].source == "recommend"
        assert result[1].category == "electronics"


# ── _normalize_per_type ─────────────────────────────────────────────────

class TestNormalizePerType:
    """Normalize each score_type group independently."""

    def test_different_types_normalized_independently(self):
        """Two groups with non-overlapping score ranges get normalized separately."""
        candidates = [
            make_candidate(1, score=10.0, score_type="structured_sort"),
            make_candidate(2, score=20.0, score_type="structured_sort"),
            make_candidate(3, score=100.0, score_type="cf"),
            make_candidate(4, score=200.0, score_type="cf"),
        ]
        result = _normalize_per_type(candidates)
        assert len(result) == 4

        # structured_sort: [10, 20] → [0.0, 1.0]
        structured = [c for c in result if c.score_type == "structured_sort"]
        assert len(structured) == 2
        structured_scores = sorted([c.score for c in structured])
        assert structured_scores == [0.0, 1.0]

        # cf: [100, 200] → [0.0, 1.0]
        cf_items = [c for c in result if c.score_type == "cf"]
        assert len(cf_items) == 2
        cf_scores = sorted([c.score for c in cf_items])
        assert cf_scores == [0.0, 1.0]

    def test_single_type(self):
        """Single score_type → behaves like _normalize_group."""
        candidates = [
            make_candidate(1, score=1.0, score_type="semantic"),
            make_candidate(2, score=2.0, score_type="semantic"),
        ]
        result = _normalize_per_type(candidates)
        assert result[0].score == 0.0
        assert result[1].score == 1.0

    def test_empty(self):
        """Empty list → empty list."""
        assert _normalize_per_type([]) == []


# ── _fuse ───────────────────────────────────────────────────────────────

class TestFuse:
    """Weighted sum fusion per product_id, respecting source weights."""

    def test_search_and_recommend_weighted(self):
        """Search candidates weighted by search_weight, rec by rec_weight."""
        candidates = [
            make_candidate(1, score=1.0, source="search", score_confidence=1.0),
            make_candidate(2, score=1.0, source="recommend", score_confidence=1.0),
        ]
        fused = _fuse(candidates, search_weight=0.7, rec_weight=0.3)
        # search: 1.0 * 0.7 * 1.0 = 0.7
        # recommend: 1.0 * 0.3 * 1.0 = 0.3
        assert fused[1] == pytest.approx(0.7)
        assert fused[2] == pytest.approx(0.3)

    def test_duplicate_id_takes_max(self):
        """Same product from multiple sources → higher adjusted score wins."""
        candidates = [
            make_candidate(1, score=0.5, source="search", score_confidence=1.0),
            make_candidate(1, score=0.9, source="recommend", score_confidence=1.0),
        ]
        # search: 0.5 * 0.7 * 1.0 = 0.35
        # recommend: 0.9 * 0.3 * 1.0 = 0.27
        # search wins (0.35 > 0.27)
        fused = _fuse(candidates, search_weight=0.7, rec_weight=0.3)
        assert len(fused) == 1
        assert fused[1] == pytest.approx(0.35)

    def test_duplicate_id_recommend_wins_when_higher(self):
        """Recommend wins when its adjusted score is higher."""
        candidates = [
            make_candidate(1, score=0.3, source="search", score_confidence=1.0),
            make_candidate(1, score=0.9, source="recommend", score_confidence=1.0),
        ]
        # search: 0.3 * 0.7 * 1.0 = 0.21
        # recommend: 0.9 * 0.3 * 1.0 = 0.27 → recommend wins
        fused = _fuse(candidates, search_weight=0.7, rec_weight=0.3)
        assert fused[1] == pytest.approx(0.27)

    def test_score_confidence_scales(self):
        """Low score_confidence reduces the effective score."""
        candidates = [
            make_candidate(1, score=1.0, source="search", score_confidence=0.5),
        ]
        fused = _fuse(candidates, search_weight=1.0, rec_weight=0.0)
        # 1.0 * 1.0 * 0.5 = 0.5
        assert fused[1] == pytest.approx(0.5)

    def test_empty_candidates(self):
        """Empty candidate list → empty dict."""
        assert _fuse([], 0.5, 0.5) == {}

    def test_equal_weights(self):
        """Equal search and rec weights give fair fusion."""
        candidates = [
            make_candidate(1, score=0.8, source="search", score_confidence=1.0),
            make_candidate(2, score=0.8, source="recommend", score_confidence=1.0),
        ]
        fused = _fuse(candidates, search_weight=0.5, rec_weight=0.5)
        # Both: 0.8 * 0.5 * 1.0 = 0.4
        assert fused[1] == pytest.approx(0.4)
        assert fused[2] == pytest.approx(0.4)


# ── _rerank_mmr ─────────────────────────────────────────────────────────

class TestRerankMMR:
    """MMR: maximize relevance - lambda * max_similarity_to_selected."""

    def make_scored(self, pairs):
        """Convert flat list of (id, score) into sorted list of tuples."""
        return sorted(pairs, key=lambda x: x[1], reverse=True)

    def test_single_item(self):
        """Single item → returned as-is."""
        scored = [(1, 0.9)]
        candidates = [make_candidate(1, score=0.9, category="books")]
        result = _rerank_mmr(scored, candidates, lambda_param=0.3)
        assert result == [(1, 0.9)]

    def test_empty_list(self):
        """Empty list → empty list (len <= 1 short-circuit)."""
        assert _rerank_mmr([], [], lambda_param=0.3) == []

    def test_same_category_penalty(self):
        """Items sharing a category get penalized in MMR ranking."""
        candidates = [
            make_candidate(1, score=0.5, category="electronics"),
            make_candidate(2, score=0.9, category="electronics"),  # highest
            make_candidate(3, score=0.8, category="books"),         # different cat
        ]
        scored = [(2, 0.9), (3, 0.8), (1, 0.5)]
        result = _rerank_mmr(scored, candidates, lambda_param=0.5)

        # First pick: id=2 (highest score 0.9)
        assert result[0] == (2, 0.9)

        # Remaining: id=3 (books, score 0.8, no penalty) vs id=1 (electronics, 0.5, penalty=0.5)
        # id=3 adjusted: 0.8 - 0.0 = 0.8
        # id=1 adjusted: 0.5 - 0.5 = 0.0
        # id=3 wins
        assert result[1][0] == 3

        # id=1 picked last
        assert result[2][0] == 1

    def test_lambda_effect(self):
        """Higher lambda → more diversity penalty."""
        candidates = [
            make_candidate(1, score=0.9, category="electronics"),
            make_candidate(2, score=0.85, category="electronics"),
        ]
        scored = [(1, 0.9), (2, 0.85)]

        # lambda=0.0: id=2 adjusted = 0.85 - 0.0 = 0.85
        result_zero = _rerank_mmr(scored, candidates, lambda_param=0.0)
        assert result_zero[1][0] == 2  # picked normally

        # lambda=1.0: id=2 adjusted = 0.85 - 1.0 = -0.15
        # But penalty is only applied if both have categories and they match
        result_high = _rerank_mmr(scored, candidates, lambda_param=1.0)
        # With penalty, id=2 still gets picked because it's the only remaining one
        assert result_high[1][0] == 2

    def test_different_categories_no_penalty(self):
        """Different categories → no penalty applied."""
        candidates = [
            make_candidate(1, score=0.9, category="books"),
            make_candidate(2, score=0.85, category="clothing"),
            make_candidate(3, score=0.8, category="electronics"),
        ]
        scored = [(1, 0.9), (2, 0.85), (3, 0.8)]
        result = _rerank_mmr(scored, candidates, lambda_param=0.5)
        # All different categories → order preserved by score
        assert [pid for pid, _ in result] == [1, 2, 3]

    def test_no_categories(self):
        """Candidates without categories → no penalty (empty category lookup)."""
        candidates = [
            make_candidate(1, score=0.9),
            make_candidate(2, score=0.85),
        ]
        scored = [(1, 0.9), (2, 0.85)]
        result = _rerank_mmr(scored, candidates, lambda_param=0.5)
        # No categories → no penalty → order preserved
        assert [pid for pid, _ in result] == [1, 2]


# ── _resolve_merge_policy ──────────────────────────────────────────────

class TestResolveMergePolicy:
    """Resolve merge policy, downgrading if incompatible with strategy."""

    def test_search_with_sql_only(self):
        """intent=search + strategy=sql_only → search policy, no downgrade.
        
        sql_only allows ['search', 'order', 'analytics', 'default'],
        and 'search' is in that list, so no downgrade is needed.
        """
        policy_key, downgraded = _resolve_merge_policy("search", "sql_only")
        assert policy_key == "search"
        assert downgraded is False

    def test_recommend_with_hybrid(self):
        """intent=recommend + strategy=hybrid → recommend policy, no downgrade."""
        policy_key, downgraded = _resolve_merge_policy("recommend", "hybrid")
        assert policy_key == "recommend"
        assert downgraded is False

    def test_recommend_with_sql_only_downgrades(self):
        """intent=recommend + strategy=sql_only → downgraded to first allowed.
        
        sql_only allows ['search', 'order', 'analytics', 'default'].
        'recommend' is NOT in that list → downgrade to 'search' (first allowed).
        """
        policy_key, downgraded = _resolve_merge_policy("recommend", "sql_only")
        assert policy_key == "search"
        assert downgraded is True

    def test_chat_with_sql_only_downgrades(self):
        """intent=chat + strategy=sql_only → downgraded (chat not in sql_only allowed)."""
        policy_key, downgraded = _resolve_merge_policy("chat", "sql_only")
        assert policy_key == "search"  # first allowed
        assert downgraded is True

    def test_unknown_intent_uses_default(self):
        """Unknown intent → 'default' policy key."""
        policy_key, downgraded = _resolve_merge_policy("nonexistent", "hybrid")
        assert policy_key == "default"
        assert downgraded is False

    def test_unknown_strategy_allows_all(self):
        """Unknown strategy → defaults to hybrid compat (allows all)."""
        policy_key, downgraded = _resolve_merge_policy("chat", "unknown_strategy")
        assert policy_key == "chat"
        assert downgraded is False

    def test_order_with_sql_only(self):
        """intent=order + strategy=sql_only → order (allowed)."""
        policy_key, downgraded = _resolve_merge_policy("order", "sql_only")
        assert policy_key == "order"
        assert downgraded is False

    def test_analytics_with_semantic_downgrades(self):
        """intent=analytics + strategy=semantic → downgraded.
        
        semantic allows ['search', 'recommend', 'chat', 'default'].
        'analytics' not in list → downgrade to 'search'.
        """
        policy_key, downgraded = _resolve_merge_policy("analytics", "semantic")
        assert policy_key == "search"
        assert downgraded is True
