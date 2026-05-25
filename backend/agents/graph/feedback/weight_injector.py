"""
Weight Injector — modulate recommendation scores using accumulated signals.

Takes the base score from the recommendation engine and adjusts it based
on the user's historical behavior signals for that product's category.

Formula:
    adjusted = base × (1 + Σ signal_weight)

Where signal_weight is the decayed, accumulated value from SignalStore.

A product in a category with high CONVERSION signals gets boosted;
a category the user has dismissed products from gets a slight penalty.
"""

from __future__ import annotations

from agents.graph.feedback.signal_store import get_user_signals


def modulate(
    base_score: float,
    category: str,
    user_id: int | None,
) -> float:
    """Apply signal-based weight adjustment to a recommendation score.

    Args:
        base_score: original score from RecommendEngine (typically 0-1 or 0-5).
        category: product category name (e.g. "Gaming Headsets").
        user_id: the user id, or None for anonymous users.

    Returns:
        Adjusted score. If user_id is None or no signals exist, returns
        base_score unchanged.
    """
    if user_id is None or not category:
        return base_score

    signals = get_user_signals(user_id)
    boost = signals.get(category, 0.0)

    # Negative signals (dismiss) are handled via NEGATIVE SignalType which
    # has negative value in SIGNAL_WEIGHTS. They flow through StandardizedSignal
    # but are excluded from ranking (RANKING_SIGNAL_TYPES only includes INTENT
    # and CONVERSION).  Dismiss effects are applied in merge_node via diversity
    # penalty, not here.
    adjusted = base_score * (1.0 + boost)

    # Floor: don't push score below 0
    return max(adjusted, 0.0)


def modulate_batch(
    items: list[dict],
    user_id: int | None,
    score_key: str = "score",
    category_key: str = "category_name",
) -> list[dict]:
    """Modulate a batch of recommendation items.

    Args:
        items: list of dicts from RecommendEngine, each with score and category.
        user_id: user id or None.
        score_key: key for the base score in each item dict.
        category_key: key for the category name in each item dict.

    Returns:
        The same list, with scores adjusted in-place. Also adds
        '_signal_boost' and '_original_score' keys for traceability.
    """
    if user_id is None or not items:
        return items

    signals = get_user_signals(user_id)
    if not signals:
        return items

    for item in items:
        cat = item.get(category_key, "")
        base = item.get(score_key, 0)
        boost = signals.get(cat, 0.0)
        item["_original_score"] = base
        item["_signal_boost"] = boost
        item[score_key] = max(base * (1.0 + boost), 0.0)

    return items
