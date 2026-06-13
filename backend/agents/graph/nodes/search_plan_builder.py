"""
SearchPlanBuilder — unified constraint extraction + grounding + strategy selection.

Single-pass query analysis producing a complete SearchPlan:
  - constraints: category, brand, budget, recipient, usage
  - signals: sort_by/direction, compare_brands
  - assessment: grounded / under_constrained
  - strategy: COMPARE / TOP_K / POPULARITY / SEMANTIC

Strategy is driven by explicit query signals only — never by intent classification.
Replaces constraint_parser.py + grounding.py (merged in Phase 5).
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from ..contracts.search_plan import (
    SearchPlan,
    QueryFrame,
    RetrievalStrategy,
    SORT_PATTERNS,
    CATEGORY_KEYWORDS,
    COMPARE_TRIGGERS,
    BRAND_ALIASES,
    normalize_query,
    parse_budget_band,
    parse_budget_range,
)
from ..commerce_intent import IntentResult
from ..lexicon import CATEGORY_LEXICON as ProductLexicon

logger = logging.getLogger(__name__)

# ── Grounding constants ───────────────────────────────────────
HIGH_INTENT_GOALS: set[str] = {
    "礼物", "送人", "送礼", "好东西", "值得买",
    "送女友", "送男朋友", "送爸妈", "送朋友", "送孩子",
    "gift", "present",
}
MAX_CLARIFY_DEPTH = 2


# ═══════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════

def build_plan(frame: QueryFrame) -> SearchPlan:
    """Build a complete SearchPlan from a QueryFrame.

    Single-pass extraction of all constraints, signals, and assessment.
    Intent from frame.intent is used only for ranking_profile downstream,
    never for strategy selection.
    """
    normalized = frame.normalized
    original = frame.raw

    # ── Constraints ──────────────────────────────────────────
    category_filter, category_confidence = _extract_category(normalized)
    brand = _extract_brand(normalized)
    budget_lower, budget_upper = _extract_budget_range(normalized, original)
    budget_band = _extract_budget_label(normalized, original)
    recipient = _extract_recipient(normalized)
    usage = _extract_usage(normalized)

    # ── Signals ──────────────────────────────────────────────
    sort_by, direction = _extract_sort(normalized)
    compare_brands: list[str] = _extract_compare_brands(normalized)

    # ── Strategy selection (constraint-driven, not intent-driven) ──
    strategy = _select_strategy(sort_by, direction, compare_brands)

    # ── State assessment ─────────────────────────────────────
    state = _assess_state(category_filter, sort_by, recipient, usage, budget_band)

    # ── Detail ───────────────────────────────────────────────
    detail_parts = []
    if sort_by:
        detail_parts.append(f"sort: {sort_by} {direction}")
    if budget_band:
        detail_parts.append(f"budget: {budget_band}")
    if compare_brands:
        detail_parts.append(f"compare: {', '.join(compare_brands)}")

    return SearchPlan(
        intent=frame.intent.intent,
        sort_by=sort_by,
        direction=direction,
        category_filter=category_filter,
        category_confidence=category_confidence,
        brand=brand,
        compare_brands=compare_brands,
        budget_lower=budget_lower,
        budget_upper=budget_upper,
        budget_band=budget_band,
        recipient=recipient,
        usage=usage,
        state=state,
        strategy=strategy,
        semantic_query=normalized,
        method="regex",
        detail=", ".join(detail_parts) if detail_parts else "no constraints detected",
    )


def parse(query: str) -> SearchPlan:
    """Backward-compatible wrapper.  Prefer build_plan(frame) for new code."""
    normalized = normalize_query(query)
    intent_result = IntentResult(intent="search", confidence=0.0, fallback="chat")
    frame = QueryFrame(raw=query, normalized=normalized, intent=intent_result)
    return build_plan(frame)


# ═══════════════════════════════════════════════════════════════
# Strategy selection (constraint-driven)
# ═══════════════════════════════════════════════════════════════

def _select_strategy(sort_by: str | None, direction: str | None,
                     compare_brands: list[str]) -> str:
    """Select retrieval strategy based on explicit query signals only."""
    if compare_brands:
        return RetrievalStrategy.COMPARE
    if sort_by == "popularity":
        return RetrievalStrategy.POPULARITY
    if sort_by:
        return RetrievalStrategy.TOP_K
    return RetrievalStrategy.SEMANTIC


# ═══════════════════════════════════════════════════════════════
# State assessment (grounding)
# ═══════════════════════════════════════════════════════════════

def _assess_state(category: str | None, sort_by: str | None,
                  recipient: str | None, usage: str | None,
                  budget_band: str | None) -> str:
    """Determine if query is GROUNDED enough to execute search.

    GROUNDED = has category OR sort OR budget OR a concrete anchor.
    UNDER_CONSTRAINED = no anchor, needs clarification.
    """
    # Concrete category → always grounded
    if category:
        return "grounded"

    # Explicit sort → browse across categories
    if sort_by:
        return "grounded"

    # Has budget + recipient/usage → grounded enough
    if budget_band and (recipient or usage):
        return "grounded"

    # Abstract goal with supporting info → grounded
    # (handled by caller — this is the simple case)

    # Nothing concrete → need clarification
    return "under_constrained"


# ═══════════════════════════════════════════════════════════════
# Constraint extractors
# ═══════════════════════════════════════════════════════════════

def _extract_sort(normalized: str) -> tuple[str | None, str | None]:
    for pattern, sb, d in SORT_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return sb, d
    return None, None


def _extract_budget_label(normalized: str, original: str) -> str | None:
    range_match = re.search(r"(\d+)\s*[-~到]\s*(\d+)", normalized)
    if range_match:
        return parse_budget_band(int(range_match.group(2)))
    under_match = re.search(r"(?:under|below|under)\s*\$?(\d+)", normalized, re.IGNORECASE)
    if under_match:
        return parse_budget_band(int(under_match.group(1)))
    within_match = re.search(r"(?:within|budget|预算)\s*\$?(\d+)", normalized, re.IGNORECASE)
    if within_match:
        return parse_budget_band(int(within_match.group(1)))
    cn_match = re.search(r"(\d+)\s*元?\s*(?:以内|以下|之内)", normalized)
    if cn_match:
        return parse_budget_band(int(cn_match.group(1)))
    above_match = re.search(r"(\d+)\s*元?\s*(?:以上|及以上|之外|以外)", normalized)
    if above_match:
        return parse_budget_band(int(above_match.group(1)), is_lower_bound=True)
    return None


def _extract_budget_range(normalized: str, original: str) -> tuple[float | None, float | None]:
    range_match = re.search(r"(\d+)\s*[-~到]\s*(\d+)", normalized)
    if range_match:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        return (lo * 0.85, hi * 1.15)
    under_match = re.search(r"(?:under|below|under)\s*\$?(\d+)", normalized, re.IGNORECASE)
    if under_match:
        return parse_budget_range(int(under_match.group(1)), is_lower_bound=False)
    within_match = re.search(r"(?:within|budget|预算)\s*\$?(\d+)", normalized, re.IGNORECASE)
    if within_match:
        return parse_budget_range(int(within_match.group(1)), is_lower_bound=False)
    cn_match = re.search(r"(\d+)\s*元?\s*(?:以内|以下|之内)", normalized)
    if cn_match:
        return parse_budget_range(int(cn_match.group(1)), is_lower_bound=False)
    above_match = re.search(r"(\d+)\s*元?\s*(?:以上|及以上|之外|以外)", normalized)
    if above_match:
        return parse_budget_range(int(above_match.group(1)), is_lower_bound=True)
    return None, None


def _extract_category(normalized: str) -> tuple[str | None, float]:
    for keyword, slug in CATEGORY_KEYWORDS.items():
        if keyword in normalized:
            return slug, 1.0
    return None, 0.0


def _extract_brand(normalized: str) -> str | None:
    for keyword, slug in BRAND_ALIASES.items():
        if keyword in normalized:
            return slug
    return None


def _extract_compare_brands(normalized: str) -> list[str]:
    # Only extract if compare trigger exists OR 2+ brands detected
    has_trigger = any(re.search(p, normalized, re.IGNORECASE) for p in COMPARE_TRIGGERS)
    brands = _multi_brand(normalized)
    if has_trigger or len(brands) >= 2:
        return brands
    return []


def _multi_brand(normalized: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for keyword, slug in BRAND_ALIASES.items():
        if keyword in normalized and slug not in seen:
            seen.add(slug)
            result.append(slug)
    return result


def _extract_recipient(normalized: str) -> str | None:
    for cn in ("女朋友", "男朋友", "妈妈", "爸爸", "爸妈", "朋友",
               "学生", "小孩", "孩子", "女友", "男友", "老婆", "老公",
               "女生", "男生", "儿童", "老人", "长辈"):
        if cn in normalized:
            return cn
    return None


def _extract_usage(normalized: str) -> str | None:
    for cn in ("学习", "工作", "游戏", "运动", "旅行", "通勤", "办公", "上课",
               "打游戏", "健身", "跑步", "看书"):
        if cn in normalized:
            return cn
    return None
