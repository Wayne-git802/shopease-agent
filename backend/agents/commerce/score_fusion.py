"""Score Fusion — three-track scoring with structured explain.

Tracks:
  popularity_score  → global product quality (reviews + rating)
  affinity_score    → user's purchase-based category preference
  feedback_score    → recent behavioral signals (INTENT + CONVERSION)

Temporal separation — affinity and feedback use different data sources:
  affinity  ← Order history (pre-session, permanent)
  feedback  ← StandardizedSignal (session-level, 90d decay)

This prevents the same purchase event from being counted twice.

All scores normalized to [0, 1]. Weights are configurable and empirically
validated via scripts/replay_validate.py (MRR@8).
"""

import math
from typing import Any


# ── Configurable weights ──────────────────────────────────────────
# Empirically validated via offline replay against 30-day purchase data.
# Swap-in point for A/B test or Bayesian optimisation.

WEIGHTS = {
    "popular":      {"alpha": 0.0, "beta": 0.0},
    "cold_start":   {"alpha": 0.0, "beta": 0.3},
    "personalized": {"alpha": 0.5, "beta": 0.5},
    "hybrid":       {"alpha": 0.3, "beta": 0.3},
}

# Normalisation caps — prevent score explosion
MAX_POP_SCORE = 12.0   # log(127+1) + 4.8×2 + 127×0.01 ≈ 11.1, headroom at 12
MAX_AFF_SCORE = 1.0    # category weight ceiling
MAX_FB_SCORE   = 1.0    # decayed signals capped


# ═══════════════════════════════════════════════════════════════════
# Track 1: Popularity (product-level, always computed)
# ═══════════════════════════════════════════════════════════════════

def popularity_score(review_count: int, avg_rating: float) -> float:
    """log(reviews+1) + rating×2 + reviews×0.01  →  quality + volume + social proof."""
    rc = review_count or 0
    rt = avg_rating or 0.0
    return math.log(rc + 1) + rt * 2.0 + rc * 0.01


def popularity_explain(review_count: int, avg_rating: float) -> str:
    rc = review_count or 0
    rt = avg_rating or 0.0
    return f"{rt:.1f}★ × {rc} reviews"


# ═══════════════════════════════════════════════════════════════════
# Track 2: Affinity (user's purchase-based category preference)
#           Data source: Order → OrderItem → Product.category
#           Pre-session, permanent — NOT from signals
# ═══════════════════════════════════════════════════════════════════

def _get_user_category_weights(user_id: int) -> dict[str, float]:
    """Build {category_name: weight} from user's purchase history.

    Weight = fraction of user's orders in this category.
    Only returns categories that appear in ≥2 purchases (noise filter).
    """
    from django.db.models import Count
    from orders.models import Order

    categories = (
        Order.objects
        .filter(user_id=user_id)
        .values('items__product__category__name')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')
    )

    weights: dict[str, float] = {}
    total = sum(c['cnt'] for c in categories)
    if total == 0:
        return weights

    for c in categories:
        name = c['items__product__category__name']
        cnt = c['cnt']
        if name and cnt >= 2:           # noise filter: at least 2 purchases
            weights[name] = cnt / total

    return weights


def affinity_score(category_name: str, user_id: int) -> tuple[float, str]:
    """Category preference score from purchase history.

    Returns:
        (normalised_score, explain_string)
    """
    if not category_name:
        return 0.0, ""
    weights = _get_user_category_weights(user_id)
    w = weights.get(category_name, 0.0)
    if w <= 0:
        return 0.0, ""
    return min(w, 1.0), f"偏好: {category_name} +{w:.2f}"


# ═══════════════════════════════════════════════════════════════════
# Track 3: Feedback (behavioral signals, 90d decay)
#           Data source: StandardizedSignal (INTENT + CONVERSION)
#           Session-level, time-decayed
# ═══════════════════════════════════════════════════════════════════

def feedback_score(category_name: str, user_id: int) -> tuple[float, str]:
    """Recent behavioral signals for a category.

    Returns:
        (normalised_score, explain_string)
    """
    if not category_name:
        return 0.0, ""
    from agents.graph.feedback.signal_store import get_user_signals
    signals = get_user_signals(user_id)
    s = signals.get(category_name, 0.0)
    if s <= 0:
        return 0.0, ""

    if s >= 0.3:
        label = f"购买信号: {category_name} +{s:.2f}"
    elif s >= 0.1:
        label = f"浏览信号: {category_name} +{s:.2f}"
    else:
        label = f"信号: {category_name} +{s:.2f}"
    return min(s, 1.0), label


# ═══════════════════════════════════════════════════════════════════
# Fusion
# ═══════════════════════════════════════════════════════════════════

def fuse(
    product: Any,
    user_id: int | None,
    strategy: str,
) -> tuple[float, dict[str, str]]:
    """Compute final score + structured explain for a single product.

    Args:
        product: Product ORM instance (needs _review_count, _average_rating, category.name).
        user_id: user id or None (None → popularity-only).
        strategy: "popular" | "cold_start" | "personalized" | "hybrid".

    Returns:
        (final_score, explain_dict)
    """
    w = WEIGHTS.get(strategy, WEIGHTS["popular"])
    explain: dict[str, str] = {}

    # Track 1 — always
    rc = getattr(product, '_review_count', None) or 0
    rt = getattr(product, '_average_rating', None) or 0.0
    pop = popularity_score(rc, rt)
    pop_norm = min(pop / MAX_POP_SCORE, 1.0)
    explain["popularity"] = popularity_explain(rc, rt)

    # Track 2 & 3 — logged-in only
    aff_norm = 0.0
    fb_norm = 0.0
    cat = product.category.name if product.category else ""

    if user_id and cat:
        aff_val, aff_exp = affinity_score(cat, user_id)
        aff_norm = aff_val
        if aff_exp:
            explain["affinity"] = aff_exp

        fb_val, fb_exp = feedback_score(cat, user_id)
        fb_norm = fb_val
        if fb_exp:
            explain["feedback"] = fb_exp

    final = pop_norm + w["alpha"] * aff_norm + w["beta"] * fb_norm
    explain["final"] = f"{final:.2f}"

    return final, explain
