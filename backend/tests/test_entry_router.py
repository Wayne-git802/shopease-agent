"""
Tests for entry_router pure functions: _tokenize, _jaccard_similarity, _fast_classify.

Floor enforcement (confidence < 0.3 → forced to "chat") is tested at the
pure-function level by verifying that _fast_classify returns low confidence
on unclassifiable input, and that the floor logic would trigger.
"""

import pytest

from agents.graph.nodes.entry_router import (
    _tokenize,
    _jaccard_similarity,
    _fast_classify,
)


# ── _tokenize ──────────────────────────────────────────────────────────

class TestTokenize:
    """Tokenize: English words + individual CJK characters + CJK bigrams."""

    def test_chinese_only(self):
        """Pure Chinese text → each char + CJK bigrams."""
        tokens = _tokenize("我想买手机")
        # Each single CJK char
        assert "我" in tokens
        assert "想" in tokens
        assert "买" in tokens
        assert "手" in tokens
        assert "机" in tokens
        # Bigrams
        assert "我想" in tokens
        assert "想买" in tokens
        assert "买手" in tokens
        assert "手机" in tokens
        # No English words
        assert "iwant" not in tokens

    def test_english_only(self):
        """Pure English → word-level tokens."""
        tokens = _tokenize("hello world")
        assert "hello" in tokens
        assert "world" in tokens
        assert len(tokens) == 2  # no CJK chars, no bigrams

    def test_mixed_chinese_english(self):
        """Mixed Chinese + English → both word tokens and CJK char/bigram tokens."""
        # Use a space to separate CJK from English so that \w+ doesn't
        # greedily consume CJK characters alongside Latin letters.
        tokens = _tokenize("你好 hello 世界")
        assert "你" in tokens
        assert "好" in tokens
        assert "世" in tokens
        assert "界" in tokens
        assert "你好" in tokens
        assert "世界" in tokens
        assert "hello" in tokens

    def test_lowercasing(self):
        """English tokens are lowercased."""
        tokens = _tokenize("Hello WORLD")
        assert "hello" in tokens
        assert "world" in tokens
        assert "Hello" not in tokens
        assert "WORLD" not in tokens

    def test_empty_string(self):
        """Empty string → empty set."""
        assert _tokenize("") == set()

    def test_punctuation_ignored(self):
        """Punctuation is not tokenized."""
        tokens = _tokenize("hello, world! 你好。")
        assert "hello" in tokens
        assert "world" in tokens
        assert "你" in tokens
        assert "好" in tokens
        assert "," not in tokens
        assert "!" not in tokens
        assert "。" not in tokens


# ── _jaccard_similarity ────────────────────────────────────────────────

class TestJaccardSimilarity:
    """Jaccard similarity between two token sets."""

    def test_identical_sets(self):
        """Two identical sets → 1.0."""
        assert _jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    def test_disjoint_sets(self):
        """Two completely disjoint sets → 0.0."""
        assert _jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        """Partial overlap gives correct fraction."""
        # a,b,c and b,c,d → intersection=2, union=4 → 0.5
        assert _jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"}) == 0.5

    def test_one_empty(self):
        """One empty set → 0.0."""
        assert _jaccard_similarity(set(), {"a", "b"}) == 0.0
        assert _jaccard_similarity({"a", "b"}, set()) == 0.0

    def test_both_empty(self):
        """Both empty → 0.0."""
        assert _jaccard_similarity(set(), set()) == 0.0


# ── _fast_classify ─────────────────────────────────────────────────────

class TestFastClassify:
    """Fast-path classification via Jaccard similarity + keyword boosting."""

    def test_chinese_commerce_query_search(self):
        """Chinese product-search query → classified as 'search'."""
        # Use explicit search keywords to ensure correct classification.
        # "搜一下" is a search keyword; "手机" adds product-related tokens.
        intent, confidence = _fast_classify("搜一下手机有哪些")
        assert intent == "search"
        assert confidence > 0.0

    def test_chinese_recommend_query(self):
        """Chinese recommendation query → classified as 'recommend'."""
        intent, confidence = _fast_classify("帮我推荐一个礼物")
        assert intent == "recommend"

    def test_english_greeting_chat(self):
        """English greeting → classified as 'chat'."""
        intent, confidence = _fast_classify("hello how are you")
        assert intent == "chat"
        assert confidence > 0.0

    def test_english_thanks_chat(self):
        """English thank-you → classified as 'chat'."""
        intent, confidence = _fast_classify("thanks bye")
        assert intent == "chat"

    def test_gibberish_low_confidence(self):
        """Random unclassifiable string → chat with low confidence."""
        intent, confidence = _fast_classify("asdfghjkl zxcvbnm qwerty")
        # Gibberish should not match any intent well; total score → 0
        # With total=0, the dict comprehension skips normalization,
        # best_intent picks max but scores are all equal → first wins.
        # Confidence will be 0.0 (or very low).
        assert confidence < 0.3

    def test_product_search_query(self):
        """Query containing product-related terms → search."""
        intent, confidence = _fast_classify("find me a laptop with good price")
        assert intent == "search"

    def test_order_status_query(self):
        """Query about order status → order."""
        intent, confidence = _fast_classify("where is my order tracking")
        assert intent == "order"

    def test_analytics_query(self):
        """Query about sales report → analytics."""
        intent, confidence = _fast_classify("show me weekly sales report")
        assert intent == "analytics"

    def test_returns_valid_intent(self):
        """Result intent is always one of the known intents."""
        for query in ["hello", "search for shoes", "recommend something",
                       "track my order", "system health", "sales report",
                       "asdfghjkl", "你好", "推荐"]:
            intent, confidence = _fast_classify(query)
            assert intent in ("search", "recommend", "order", "ops",
                              "analytics", "chat")

    def test_confidence_in_range(self):
        """Confidence is always in [0, 1]."""
        for query in ["hello", "find product", "random gibberish xyz"]:
            _, confidence = _fast_classify(query)
            assert 0.0 <= confidence <= 1.0


# ── Floor enforcement (logic verification) ─────────────────────────────

class TestFloorEnforcement:
    """Verify the floor enforcement logic: confidence < 0.3 → forced 'chat'."""

    def test_gibberish_triggers_floor(self):
        """Gibberish returns confidence < 0.3, which would trigger floor."""
        _, confidence = _fast_classify("asdfghjkl12345!!!")
        # The floor logic in entry_router() checks: if confidence < 0.3 → force chat.
        # Here we verify _fast_classify produces low-enough confidence.
        assert confidence < 0.3, (
            f"Expected confidence < 0.3 for gibberish, got {confidence}"
        )

    def test_meaningful_query_above_floor(self):
        """Meaningful query should have confidence >= 0.3."""
        _, confidence = _fast_classify("I want to buy a laptop")
        assert confidence >= 0.3, (
            f"Expected confidence >= 0.3 for meaningful query, got {confidence}"
        )
