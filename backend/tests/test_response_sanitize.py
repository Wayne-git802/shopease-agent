"""
Tests for response._sanitize — banned phrase detection.
Pure function, no DB, no state.
"""
import pytest
from agents.graph.response import _sanitize, BANNED_PHRASES, _SANITIZE_REPLACEMENT


class TestSanitize:
    def test_clean_text_passes_through(self):
        assert _sanitize("为您推荐以下几款手机：") == "为您推荐以下几款手机："

    def test_empty_text_returns_empty(self):
        assert _sanitize("") == ""

    def test_none_text_returns_none(self):
        assert _sanitize(None) is None

    def test_banned_phrase_triggers_replacement(self):
        result = _sanitize("已为您转接人工客服，请稍等")
        assert result == _SANITIZE_REPLACEMENT

    def test_退款已到账_triggers(self):
        result = _sanitize("您的退款已到账，请注意查收")
        assert result == _SANITIZE_REPLACEMENT

    def test_已发货_triggers(self):
        result = _sanitize("您的订单已发货，物流单号是SF123456")
        assert result == _SANITIZE_REPLACEMENT

    def test_取消订单_triggers(self):
        result = _sanitize("已为您取消订单")
        assert result == _SANITIZE_REPLACEMENT

    def test_人工客服_triggers(self):
        result = _sanitize("已经帮您通知人工客服了")
        assert result == _SANITIZE_REPLACEMENT

    def test_banned_phrase_embedded_in_text(self):
        """Banned phrase anywhere in response → replacement."""
        result = _sanitize("感谢您的耐心等待。退款已到账，请查收。如有疑问请联系我们。")
        assert result == _SANITIZE_REPLACEMENT

    def test_all_banned_phrases_are_non_empty(self):
        for phrase in BANNED_PHRASES:
            assert phrase, f"Banned phrase should not be empty"
            assert len(phrase) >= 2, f"Banned phrase too short (risk of false positive): '{phrase}'"

    def test_sanitize_replacement_is_not_empty(self):
        assert _SANITIZE_REPLACEMENT
        assert len(_SANITIZE_REPLACEMENT) > 10
