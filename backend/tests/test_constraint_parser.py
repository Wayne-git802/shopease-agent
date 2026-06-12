"""
Tests for constraint_parser — sort / budget / category / brand extraction.
All pure functions, no DB, no LLM.
"""
import pytest
from agents.graph.nodes.constraint_parser import (
    _extract_sort,
    _extract_category,
    _extract_brand,
    _extract_budget_range,
    _extract_budget_label,
)

# ═══════════════════════════════════════════════════════════════
# _extract_category
# ═══════════════════════════════════════════════════════════════

class TestExtractCategory:
    def test_手机_maps_to_smartphone_with_confidence_1(self):
        slug, conf = _extract_category("手机")
        assert slug == "智能手机"
        assert conf == 1.0

    def test_耳机_maps_to_headphones(self):
        slug, conf = _extract_category("耳机")
        assert slug == "耳机"
        assert conf == 1.0

    def test_english_phone_maps_to_smartphone(self):
        slug, conf = _extract_category("smartphone phone")
        assert slug == "智能手机"
        assert conf == 1.0

    def test_laptop_maps_correctly(self):
        slug, conf = _extract_category("laptop")
        assert slug == "笔记本电脑"
        assert conf == 1.0

    def test_no_match_returns_none(self):
        slug, conf = _extract_category("今天天气真好")
        assert slug is None
        assert conf == 0.0

    def test_empty_string_returns_none(self):
        slug, conf = _extract_category("")
        assert slug is None
        assert conf == 0.0

    def test_multiple_keywords_first_wins(self):
        # "手机" comes before "耳机" in CATEGORY_KEYWORDS iteration
        slug, conf = _extract_category("手机和耳机")
        assert slug is not None
        assert conf == 1.0


# ═══════════════════════════════════════════════════════════════
# _extract_sort
# ═══════════════════════════════════════════════════════════════

class TestExtractSort:
    def test_最贵_returns_price_desc(self):
        sb, d = _extract_sort("最贵的手机")
        assert sb == "price"
        assert d == "desc"

    def test_最便宜_returns_price_asc(self):
        sb, d = _extract_sort("最便宜的耳机")
        assert sb == "price"
        assert d == "asc"

    def test_评分高_returns_rating_desc(self):
        sb, d = _extract_sort("评分最高的显示器")
        assert sb == "rating"
        assert d == "desc"

    def test_最新_returns_created_at_desc(self):
        sb, d = _extract_sort("最新上架的笔记本电脑")
        assert sb == "created_at"
        assert d == "desc"

    def test_热门_returns_popularity_desc(self):
        sb, d = _extract_sort("最热门的键盘")
        assert sb == "popularity"
        assert d == "desc"

    def test_cheap_returns_price_asc(self):
        sb, d = _extract_sort("cheap headphones")
        assert sb == "price"
        assert d == "asc"

    def test_expensive_returns_price_desc(self):
        sb, d = _extract_sort("most expensive laptop")
        assert sb == "price"
        assert d == "desc"

    def test_newest_returns_created_at_desc(self):
        sb, d = _extract_sort("newest monitors")
        assert sb == "created_at"
        assert d == "desc"

    def test_popular_returns_popularity_desc(self):
        sb, d = _extract_sort("popular watches")
        assert sb == "popularity"
        assert d == "desc"

    def test_no_sort_returns_none(self):
        sb, d = _extract_sort("推荐一款手机")
        assert sb is None
        assert d is None

    def test_under_below_returns_price_asc(self):
        sb, d = _extract_sort("under 500 headphones")
        assert sb == "price"
        assert d == "asc"


# ═══════════════════════════════════════════════════════════════
# _extract_brand
# ═══════════════════════════════════════════════════════════════

class TestExtractBrand:
    def test_华为_extracts_huawei(self):
        assert _extract_brand("华为手机") == "华为"

    def test_apple_extracts_apple(self):
        assert _extract_brand("apple watch") == "苹果"

    def test_samsung_extracts_samsung(self):
        assert _extract_brand("Samsung galaxy") == "三星"

    def test_索尼_extracts_sony(self):
        assert _extract_brand("索尼耳机") == "索尼"

    def test_logitech_extracts_logitech(self):
        assert _extract_brand("Logitech键盘") == "罗技"

    def test_no_brand_returns_none(self):
        assert _extract_brand("推荐一款手机") is None

    def test_empty_returns_none(self):
        assert _extract_brand("") is None


# ═══════════════════════════════════════════════════════════════
# _extract_budget_range
# ═══════════════════════════════════════════════════════════════

class TestExtractBudgetRange:
    def test_explicit_range(self):
        lo, hi = _extract_budget_range("1000-3000手机", "1000-3000手机")
        assert lo == 850.0   # 1000 * 0.85
        assert hi == 3450.0  # 3000 * 1.15

    def test_under_english(self):
        lo, hi = _extract_budget_range("under 500 headphones", "under 500 headphones")
        assert lo is None
        assert hi == 650.0    # 500 * 1.3

    def test_within_english(self):
        lo, hi = _extract_budget_range("within 2000 laptop", "within 2000 laptop")
        assert lo is None
        assert hi == 2600.0   # 2000 * 1.3

    def test_以内_chinese(self):
        lo, hi = _extract_budget_range("500元以内的耳机", "500元以内的耳机")
        assert lo is None
        assert hi == 650.0

    def test_以上_chinese(self):
        lo, hi = _extract_budget_range("1000元以上的手机", "1000元以上的手机")
        assert lo == 700.0    # 1000 * 0.7
        assert hi is None

    def test_以下_chinese(self):
        lo, hi = _extract_budget_range("300以下", "300以下")
        assert lo is None
        assert hi == 390.0    # 300 * 1.3

    def test_no_budget_returns_none(self):
        lo, hi = _extract_budget_range("推荐手机", "推荐手机")
        assert lo is None
        assert hi is None

    def test_empty_returns_none(self):
        lo, hi = _extract_budget_range("", "")
        assert lo is None
        assert hi is None


# ═══════════════════════════════════════════════════════════════
# _extract_budget_label
# ═══════════════════════════════════════════════════════════════

class TestExtractBudgetLabel:
    def test_under_500_returns_band(self):
        assert _extract_budget_label("under 500 headphones", "") == "0-500"

    def test_1500_plus(self):
        assert _extract_budget_label("within 2000 laptop", "") == "1500+"

    def test_500_to_1500(self):
        assert _extract_budget_label("1000以内的耳机", "") == "500-1500"
