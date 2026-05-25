"""
ConstraintParser — unified entry point for query classification.

Single function: `parse(query) -> SearchPlan`

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
    QueryIntent,
    RetrievalStrategy,
    SORT_PATTERNS,
    BUDGET_PATTERNS,
    CATEGORY_KEYWORDS,
    RECOMMEND_TRIGGERS,
    normalize_query,
    parse_budget_band,
    VALID_SORT_FIELDS,
    VALID_DIRECTIONS,
)

logger = logging.getLogger(__name__)


def parse(query: str) -> SearchPlan:
    """Parse a user query into a SearchPlan.

    Four-step pipeline:
      1. Intent classification (regex → sort | recommend | ambiguous)
      2. Sort field extraction (when intent=sort)
      3. Budget band extraction
      4. UX hint decisions

    Args:
        query: Raw user input (Chinese or English)

    Returns:
        SearchPlan with intent, sort, budget, hints resolved.
    """
    normalized = normalize_query(query)
    original = query

    # ── Step 1: Intent classification ──────────────────────────
    intent, sort_by, direction = _classify_intent(normalized, original)

    # ── Step 2: Budget extraction ──────────────────────────────
    budget_band = _extract_budget(normalized, original)

    # ── Step 3: Category extraction ────────────────────────────
    category_filter = _extract_category(normalized)

    # ── Step 4: Hint decisions ─────────────────────────────────
    show_budget_hint = False
    show_clarify_hint = False

    if intent == QueryIntent.SORT:
        # Hard constraint: no hints needed
        pass
    elif intent == QueryIntent.RECOMMEND:
        show_budget_hint = not bool(budget_band)  # hint if budget not already set
    elif intent == QueryIntent.AMBIGUOUS:
        show_clarify_hint = True
        show_budget_hint = True

    # ── Build SearchPlan ───────────────────────────────────────

    strategy = (
        RetrievalStrategy.STRUCTURED_SORT
        if intent == QueryIntent.SORT and sort_by
        else RetrievalStrategy.SEMANTIC
    )

    detail_parts = []
    if intent == QueryIntent.SORT:
        detail_parts.append(f"sort: {sort_by} {direction}")
    if budget_band:
        detail_parts.append(f"budget: {budget_band}")
    if show_clarify_hint:
        detail_parts.append("clarify_hint")

    return SearchPlan(
        intent=intent,
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


# ═══════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════

def _classify_intent(
    normalized: str, original: str
) -> tuple[str, Optional[str], Optional[str]]:
    """Classify intent and extract sort fields.

    Priority order:
      1. Check SORT_PATTERNS → intent=sort
      2. Check RECOMMEND_TRIGGERS → intent=recommend
      3. Check for pure sort keywords (price, rating, etc.) without triggers
      4. Fallback → ambiguous

    Returns:
        (intent, sort_by, direction)
    """
    # ── Check hard sort patterns ──
    for pattern, sb, d in SORT_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return QueryIntent.SORT, sb, d

    # ── Check recommend triggers ──
    for pattern in RECOMMEND_TRIGGERS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return QueryIntent.RECOMMEND, None, None

    # ── Check for implicit sort words (price/rating/new without trigger) ──
    implicit_sort = [
        (r"^(?:最|most|top|best).*(?:贵|便宜|cheap|expensive|price)", "price", "desc"),
        (r"\b(?:under|below)\b.*\d+", "price", "asc"),   # "under 500" → cheapest first
    ]
    for pattern, sb, d in implicit_sort:
        if re.search(pattern, normalized, re.IGNORECASE):
            return QueryIntent.SORT, sb, d

    # ── Check for category hint → implicit recommend ──
    # "gaming headset", "耳机" — product mention without sort/trigger = recommend
    if _extract_category(normalized):
        return QueryIntent.RECOMMEND, None, None

    # ── Default: ambiguous ──
    return QueryIntent.AMBIGUOUS, None, None


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
