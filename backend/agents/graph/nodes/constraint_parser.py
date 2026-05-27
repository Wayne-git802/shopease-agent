"""
SearchPlanBuilder — constraint extraction from a QueryFrame.

CONTRACT: SearchPlanBuilder ONLY extracts structured constraints.
It accepts intent from IntentClassifier as INPUT, not as something to re-derive.

Entry points:
  - build_plan(frame)  → SearchPlan   (new, primary)
  - parse(query)        → SearchPlan   (deprecated wrapper)

Replaces scattered detection logic in:
  - orchestrator.sort_precheck
  - search_node.detect_sort_intent
  - entry_router._fast_classify

Produces a SearchPlan v2 consumed by all downstream nodes.
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
    BUDGET_PATTERNS,
    CATEGORY_KEYWORDS,
    normalize_query,
    parse_budget_band,
    VALID_SORT_FIELDS,
    VALID_DIRECTIONS,
)
from ..commerce_intent import IntentResult

logger = logging.getLogger(__name__)


def build_plan(frame: QueryFrame) -> SearchPlan:
    """Build a SearchPlan from a QueryFrame.

    Extracts sort, budget, and category constraints from the query text.
    Uses frame.intent.intent as the authoritative intent — does NOT re-derive it.

    Pipeline:
      1. Read authoritative intent from frame.intent.intent
      2. Extract sort field + direction (regex)
      3. Extract budget band
      4. Extract category filter
      5. Decide hints and strategy

    Args:
        frame: QueryFrame with raw query, normalized query, and IntentResult

    Returns:
        SearchPlan with intent, sort, budget, hints resolved.
    """
    normalized = frame.normalized
    original = frame.raw

    # ── Step 0: Authoritative intent from IntentClassifier ──────
    intent_str = frame.intent.intent  # "search" | "recommend" | "order" | "analytics"

    # ── Step 1: Sort extraction ─────────────────────────────────
    sort_by, direction = _extract_sort(normalized)

    # ── Step 2: Budget extraction ───────────────────────────────
    budget_band = _extract_budget(normalized, original)

    # ── Step 3: Category extraction ─────────────────────────────
    category_filter = _extract_category(normalized)

    # ── Step 4: Strategy selection ──────────────────────────────
    strategy = (
        RetrievalStrategy.STRUCTURED_SORT
        if sort_by
        else RetrievalStrategy.SEMANTIC
    )

    # ── Step 5: Hint decisions ──────────────────────────────────
    show_budget_hint = False
    show_clarify_hint = False

    if intent_str == "recommend":
        show_budget_hint = not bool(budget_band)  # hint if budget not already set
    elif intent_str == "order":
        # Order intent: no search hints needed
        pass
    elif intent_str == "analytics":
        # Analytics intent: no search hints needed
        pass

    # ── Build detail string ─────────────────────────────────────
    detail_parts = []
    if sort_by:
        detail_parts.append(f"sort: {sort_by} {direction}")
    if budget_band:
        detail_parts.append(f"budget: {budget_band}")
    if show_clarify_hint:
        detail_parts.append("clarify_hint")

    return SearchPlan(
        intent=intent_str,
        sort_by=sort_by,
        direction=direction,
        category_filter=category_filter,
        budget_band=budget_band,
        strategy=strategy,
        semantic_query=normalized,
        show_clarify_hint=show_clarify_hint,
        show_budget_hint=show_budget_hint,
        method="regex",
        detail=", ".join(detail_parts) if detail_parts else "no constraints detected",
    )


def parse(query: str) -> SearchPlan:
    """Parse a user query into a SearchPlan.  [DEPRECATED]

    Backward-compatible wrapper around build_plan().
    Creates a minimal QueryFrame with a default IntentResult.

    Prefer build_plan(frame) for new code.

    Args:
        query: Raw user input (Chinese or English)

    Returns:
        SearchPlan with intent, sort, budget, hints resolved.
    """
    normalized = normalize_query(query)
    intent_result = IntentResult(intent="search", confidence=0.0, fallback="chat")
    frame = QueryFrame(raw=query, normalized=normalized, intent=intent_result)
    return build_plan(frame)


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════

def _extract_sort(normalized: str) -> tuple[Optional[str], Optional[str]]:
    """Extract sort field and direction from query text.

    Checks SORT_PATTERNS and implicit sort patterns.
    Does NOT re-derive intent — pure constraint extraction.

    Returns:
        (sort_by, direction) or (None, None)
    """
    # ── Check hard sort patterns ──
    for pattern, sb, d in SORT_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return sb, d

    # ── Check for implicit sort words (price/rating/new without trigger) ──
    implicit_sort = [
        (r"^(?:最|most|top|best).*(?:贵|便宜|cheap|expensive|price)", "price", "desc"),
        (r"\b(?:under|below)\b.*\d+", "price", "asc"),   # "under 500" → cheapest first
    ]
    for pattern, sb, d in implicit_sort:
        if re.search(pattern, normalized, re.IGNORECASE):
            return sb, d

    return None, None


def _extract_budget(normalized: str, original: str) -> Optional[str]:
    """Extract budget band from query text.

    Handles:
      - "1000-3000" → "1000-3000" → parse_budget_band takes hi
      - "under 500" → "0-500"
      - "500以内" → "0-500"
      - "within 2000" → "1500+"

    Returns band label or None.
    """
    # Pattern: explicit range like "1000-3000" / "1000到3000"
    range_match = re.search(r"(\d+)\s*[-~到]\s*(\d+)", normalized)
    if range_match:
        hi = int(range_match.group(2))
        return parse_budget_band(hi)

    # Pattern: "under 500" / "below 500"
    under_match = re.search(r"(?:under|below|under)\s*\$?(\d+)", normalized, re.IGNORECASE)
    if under_match:
        amt = int(under_match.group(1))
        return parse_budget_band(amt)

    # Pattern: "within 2000" / "budget 2000"
    within_match = re.search(r"(?:within|budget|预算)\s*\$?(\d+)", normalized, re.IGNORECASE)
    if within_match:
        amt = int(within_match.group(1))
        return parse_budget_band(amt)

    # Pattern: "500以内" / "500以下"
    cn_match = re.search(r"(\d+)\s*(?:以内|以下|之内)", normalized)
    if cn_match:
        amt = int(cn_match.group(1))
        return parse_budget_band(amt)

    return None


def _extract_category(normalized: str) -> Optional[str]:
    """Extract product category from query keywords.

    Returns category slug (English) or None.
    """
    for keyword, slug in CATEGORY_KEYWORDS.items():
        if keyword in normalized:
            return slug
    return None
