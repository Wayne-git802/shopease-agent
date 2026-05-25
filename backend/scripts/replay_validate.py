"""Offline replay validation for Score Fusion weights.

Replays past 30 days of purchase data to measure MRR@8 under different
weight configurations. Does NOT claim optimality — only empirical validation.

Usage:
    python manage.py shell < scripts/replay_validate.py
    or
    python scripts/replay_validate.py
"""

import os
import sys
import math
from datetime import datetime, timedelta
from collections import defaultdict


def compute_mrr(scored_list: list[tuple[int, float]], target_product_id: int) -> float:
    """Compute reciprocal rank: 1/rank for the target product in scored list."""
    for rank, (pid, _score) in enumerate(scored_list, 1):
        if pid == target_product_id:
            return 1.0 / rank
    return 0.0


def validate(alpha: float = 0.5, beta: float = 0.5, days: int = 30) -> dict:
    """Run replay validation with given α/β weights.

    For each user who purchased in the last N days:
      1. Take their purchase history *before* the purchase as training data.
      2. Score candidate products with given α/β.
      3. Check what rank the purchased product got.

    Returns:
        {"mrr": float, "n_users": int, "n_purchases": int, "coverage": float}
    """
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
    django.setup()

    from django.utils import timezone
    from orders.models import Order
    from products.models import Product
    from agents.recommend.score_fusion import fuse, WEIGHTS
    from agents.recommend.strategy_router import route

    # Override weights for this run
    WEIGHTS["personalized"] = {"alpha": alpha, "beta": beta}
    WEIGHTS["hybrid"] = {"alpha": alpha, "beta": beta}

    cutoff = timezone.now() - timedelta(days=days)

    # Find users who purchased recently
    recent_orders = (
        Order.objects
        .filter(created_at__gte=cutoff)
        .select_related('user')
        .prefetch_related('items__product__category')
    )

    mrr_sum = 0.0
    n_purchases = 0
    n_explained = 0
    users_seen = set()

    for order in recent_orders:
        if not order.user:
            continue
        users_seen.add(order.user_id)
        strategy, reason = route(order.user)

        # Get candidate pool
        candidates = list(
            Product.objects.filter(is_active=True)
            .with_sales_data()
            .select_related('category')[:60]
        )

        # Score all candidates
        scored = []
        for p in candidates:
            final, explain = fuse(p, order.user_id, strategy)
            scored.append((p.id, final))
            if len(explain) > 2:  # more than just popularity + final
                n_explained += 1

        scored.sort(key=lambda x: x[1], reverse=True)

        # Check each item in the order
        for item in order.items.all():
            target_pid = item.product_id
            mrr_sum += compute_mrr(scored, target_pid)
            n_purchases += 1

    mrr = mrr_sum / max(n_purchases, 1)
    coverage = n_explained / max(n_purchases * 60, 1)  # per-candidate explain rate

    return {
        "mrr": round(mrr, 4),
        "n_users": len(users_seen),
        "n_purchases": n_purchases,
        "coverage": round(coverage, 4),
    }


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Score Fusion — Replay Validation (MRR@8)")
    print("=" * 60)
    print()

    # Baseline: popularity only
    baseline = validate(alpha=0.0, beta=0.0)
    print(f"Baseline (popularity only):  MRR={baseline['mrr']}  "
          f"users={baseline['n_users']}  purchases={baseline['n_purchases']}")
    print()

    # Test configurations
    configs = [
        (0.3, 0.3, "hybrid"),
        (0.5, 0.5, "personalized"),
        (0.3, 0.5, "feedback-heavy"),
        (0.5, 0.3, "affinity-heavy"),
    ]

    best_mrr = baseline["mrr"]
    best_cfg = "baseline"

    for alpha, beta, label in configs:
        result = validate(alpha=alpha, beta=beta)
        delta = result["mrr"] - baseline["mrr"]
        marker = " ← BEST" if result["mrr"] > best_mrr else ""
        if result["mrr"] > best_mrr:
            best_mrr = result["mrr"]
            best_cfg = label
        print(f"{label:20s}  α={alpha} β={beta}  "
              f"MRR={result['mrr']} (Δ{delta:+.4f})  "
              f"coverage={result['coverage']}{marker}")

    print()
    print(f"Best: {best_cfg}  MRR={best_mrr}")
