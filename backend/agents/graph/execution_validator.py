"""
Execution Validator — validates SearchPlan before node consumption.

Placed between ConstraintParser and downstream nodes (search_node,
recommend_node).  Does NOT re-derive intent — only validates and
corrects unreasonable plan configurations that cause execution drift.

Responsibilities:
  1. Validate structured sort plans — ensure sort_by is reasonable for query
  2. Validate recommend_type — reject invalid types, resolve from context
  3. Confidence gate — downgrade structured plans when confidence < threshold
  4. Output: ValidatedPlan with corrections logged

Every validation decision is recorded in decision_log for trace/replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal

from .contracts.search_plan import (
    SearchPlan,
    RetrievalStrategy,
    VALID_SORT_FIELDS,
    VALID_DIRECTIONS,
)


# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

# Minimum confidence required to accept a structured sort plan
STRUCTURED_CONFIDENCE_THRESHOLD = 0.4

# Valid recommend_type values
VALID_RECOMMEND_TYPES = {"for-you", "popular", "trending", "similar"}

# When sort_by conflicts with query semantics, downgrade
# (sort_by, direction) → keywords that should be present for it to make sense
SORT_SEMANTIC_CHECKS: dict[tuple[str, str], list[str]] = {
    ("price", "asc"):  ["便宜", "cheap", "低价", "最便宜", "划算", "实惠", "lowest"],
    ("price", "desc"): ["贵", "expensive", "高价", "最贵", "高端", "旗舰"],
    ("rating", "desc"): ["评分", "评价", "口碑", "rating", "高评", "好评"],
    ("popularity", "desc"): ["热门", "流行", "畅销", "popular", "trending", "hot", "火"],
    ("created_at", "desc"): ["最新", "新款", "new", "latest", "最近", "刚上"],
}


# ═══════════════════════════════════════════════════════════════
# Decision Log (single entry per validation)
# ═══════════════════════════════════════════════════════════════

@dataclass
class ValidationDecision:
    """Record of a single validation action — for trace/replay."""
    rule: str                    # e.g. "sort_semantic_mismatch"
    action: Literal["downgrade", "correct", "reject", "warn"]
    field: str                   # which field was changed
    original: str                # original value (truncated)
    corrected: str               # new value (truncated)
    reason: str                  # human-readable reason

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "action": self.action,
            "field": self.field,
            "original": self.original,
            "corrected": self.corrected,
            "reason": self.reason,
        }


# ═══════════════════════════════════════════════════════════════
# Validated Plan
# ═══════════════════════════════════════════════════════════════

@dataclass
class ValidatedPlan:
    """SearchPlan after validation — the canonical input to downstream nodes."""
    plan: SearchPlan
    decisions: list[ValidationDecision] = field(default_factory=list)
    downgraded: bool = False

    def to_dict(self) -> dict:
        d = self.plan.to_dict()
        d["_validated"] = True
        d["_downgraded"] = self.downgraded
        d["_decisions"] = [dec.to_dict() for dec in self.decisions]
        return d


# ═══════════════════════════════════════════════════════════════
# Rule 1: Sort semantic validation
# ═══════════════════════════════════════════════════════════════

def _validate_sort_semantics(
    plan: SearchPlan, query: str
) -> tuple[SearchPlan, list[ValidationDecision]]:
    """
    If plan.is_structured() but the sort_by/direction doesn't match
    query semantics, downgrade to semantic search.
    """
    decisions: list[ValidationDecision] = []
    if not plan.is_structured():
        return plan, decisions

    assert plan.sort_by is not None and plan.direction is not None
    sort_by = plan.sort_by
    direction = plan.direction

    # Validate field/direction are legal
    if sort_by not in VALID_SORT_FIELDS:
        decisions.append(ValidationDecision(
            rule="sort_field_invalid",
            action="downgrade",
            field="sort_by",
            original=sort_by,
            corrected="<semantic>",
            reason=f"'{sort_by}' not in valid fields: {VALID_SORT_FIELDS}",
        ))
        return _downgrade_to_semantic(plan, decisions), decisions

    if direction not in VALID_DIRECTIONS:
        decisions.append(ValidationDecision(
            rule="sort_direction_invalid",
            action="downgrade",
            field="direction",
            original=direction,
            corrected="<semantic>",
            reason=f"'{direction}' not in valid directions: {VALID_DIRECTIONS}",
        ))
        return _downgrade_to_semantic(plan, decisions), decisions

    # Semantic check: does query contain keywords matching sort intent?
    key = (sort_by, direction)
    expected_keywords = SORT_SEMANTIC_CHECKS.get(key)
    if expected_keywords:
        if not any(kw in query for kw in expected_keywords):
            # Also check: if there's a category_filter, price sort is acceptable
            # because "最便宜的耳机" → category helps narrow
            if sort_by == "price" and plan.category_filter:
                return plan, decisions  # OK — category narrows it

            decisions.append(ValidationDecision(
                rule="sort_semantic_mismatch",
                action="downgrade",
                field="strategy",
                original=f"{sort_by}_{direction}",
                corrected="semantic",
                reason=(
                    f"Query has no {sort_by}/{direction} keywords; "
                    f"expected: {expected_keywords[:3]}..."
                ),
            ))
            return _downgrade_to_semantic(plan, decisions), decisions

    return plan, decisions


# ═══════════════════════════════════════════════════════════════
# Rule 2: Confidence gate
# ═══════════════════════════════════════════════════════════════

def _validate_confidence(
    plan: SearchPlan, commerce_confidence: float
) -> tuple[SearchPlan, list[ValidationDecision]]:
    """
    If plan.is_structured() but commerce intent confidence is below
    threshold, downgrade to semantic — structured sort is a strong claim.
    """
    decisions: list[ValidationDecision] = []
    if not plan.is_structured():
        return plan, decisions

    if commerce_confidence < STRUCTURED_CONFIDENCE_THRESHOLD:
        decisions.append(ValidationDecision(
            rule="confidence_gate",
            action="downgrade",
            field="strategy",
            original=f"structured (conf={commerce_confidence})",
            corrected="semantic",
            reason=(
                f"Commerce confidence {commerce_confidence} < "
                f"threshold {STRUCTURED_CONFIDENCE_THRESHOLD}"
            ),
        ))
        return _downgrade_to_semantic(plan, decisions), decisions

    return plan, decisions


# ═══════════════════════════════════════════════════════════════
# Rule 3: recommend_type validation
# ═══════════════════════════════════════════════════════════════

def _validate_recommend_type(
    recommend_type: str,
    intent: str,
    user_id: int | None,
    has_history: bool,
) -> tuple[str, list[ValidationDecision]]:
    """
    Validate and correct recommend_type.
    - Empty/invalid → resolve from context
    - "for-you" but no user history → "popular"
    """
    decisions: list[ValidationDecision] = []

    if recommend_type in VALID_RECOMMEND_TYPES:
        # "for-you" requires user history
        if recommend_type == "for-you" and not has_history:
            decisions.append(ValidationDecision(
                rule="recommend_no_history",
                action="correct",
                field="recommend_type",
                original="for-you",
                corrected="popular",
                reason="User has no purchase history — cannot personalize",
            ))
            return "popular", decisions
        return recommend_type, decisions

    # Invalid or empty — resolve
    original = recommend_type or "<empty>"
    if intent == "recommend" and user_id and has_history:
        corrected = "for-you"
    else:
        corrected = "popular"

    decisions.append(ValidationDecision(
        rule="recommend_type_resolve",
        action="correct",
        field="recommend_type",
        original=original,
        corrected=corrected,
        reason=(
            f"Resolved from intent={intent}, user_id={user_id}, "
            f"has_history={has_history}"
        ),
    ))
    return corrected, decisions


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _downgrade_to_semantic(plan: SearchPlan) -> SearchPlan:
    """Return a copy of plan downgraded to semantic strategy."""
    return SearchPlan(
        intent=plan.intent,
        sort_by=None,
        direction=None,
        category_filter=plan.category_filter,
        budget_band=plan.budget_band,
        strategy=RetrievalStrategy.SEMANTIC,
        semantic_query=plan.semantic_query,
        show_clarify_hint=plan.show_clarify_hint,
        show_budget_hint=plan.show_budget_hint,
        method=f"{plan.method}+validated",
        detail=f"Downgraded from structured: {plan.detail}",
    )


# ═══════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════

def validate(
    plan: SearchPlan,
    query: str,
    commerce_confidence: float = 0.5,
    recommend_type: str = "",
    intent: str = "recommend",
    user_id: int | None = None,
    has_history: bool = False,
) -> ValidatedPlan:
    """
    Validate a SearchPlan before it's consumed by downstream nodes.

    Pipeline:
      1. Sort semantic check — does query match sort_by/direction?
      2. Confidence gate — is structured sort warranted?
      3. recommend_type resolution — valid + appropriate?

    Returns a ValidatedPlan with all corrections applied and logged.
    """
    all_decisions: list[ValidationDecision] = []
    downgraded = False

    # Rule 1: Sort semantics
    plan, decs = _validate_sort_semantics(plan, query)
    all_decisions.extend(decs)

    # Rule 2: Confidence gate (only if still structured after rule 1)
    plan, decs = _validate_confidence(plan, commerce_confidence)
    all_decisions.extend(decs)

    if any(d.action == "downgrade" for d in all_decisions):
        downgraded = True

    # Rule 3: recommend_type (doesn't modify plan, returns corrected type)
    rec_type, decs = _validate_recommend_type(
        recommend_type, intent, user_id, has_history
    )
    all_decisions.extend(decs)

    return ValidatedPlan(
        plan=plan,
        decisions=all_decisions,
        downgraded=downgraded,
    )


# ═══════════════════════════════════════════════════════════════
# Convenience: extract validated recommend_type
# ═══════════════════════════════════════════════════════════════

def get_validated_recommend_type(vp: ValidatedPlan) -> str:
    """
    Extract the validated recommend_type from decisions.
    Falls back to "popular" if no correction was made.
    """
    for d in vp.decisions:
        if d.field == "recommend_type":
            return d.corrected
    return "popular"
