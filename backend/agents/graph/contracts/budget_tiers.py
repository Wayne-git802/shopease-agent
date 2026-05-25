"""
Dynamic budget range calculator — analyzes product price distribution
and generates meaningful budget tiers for the UI.

Runs once at import time, caches results in memory.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Cached result
_budget_tiers: Optional[list[dict]] = None


def compute_budget_tiers() -> list[dict]:
    """Analyze product prices and return budget tiers optimized for the actual data.

    Returns list of {label, lo, hi} dicts.
    Labels use plain numbers; ¥ is added by the frontend.
    """
    global _budget_tiers
    if _budget_tiers is not None:
        return _budget_tiers

    try:
        from django.db import connection

        with connection.cursor() as c:
            c.execute("SELECT price FROM products WHERE price > 0 ORDER BY price")
            prices = [r[0] for r in c.fetchall()]

        if not prices:
            logger.warning("No products with prices, using fallback tiers")
            _budget_tiers = _fallback_tiers()
            return _budget_tiers

        n = len(prices)

        def pct(p: float) -> float:
            idx = min(int(n * p / 100), n - 1)
            return prices[idx]

        # Generate tiers based on actual distribution
        # Use natural breaks at P10, P30, P60, P85, and cap
        p10 = round(pct(10))
        p30 = round(pct(30))
        p60 = round(pct(60))
        p85 = round(pct(85))

        tiers = [
            {"label": f"0 - {p10}", "lo": 0, "hi": p10},
            {"label": f"{p10} - {p30}", "lo": p10, "hi": p30},
            {"label": f"{p30} - {p60}", "lo": p30, "hi": p60},
            {"label": f"{p60} - {p85}", "lo": p60, "hi": p85},
            {"label": f"{p85}+", "lo": p85, "hi": 999999},
        ]

        _budget_tiers = tiers
        logger.info(f"Dynamic budget tiers: {[(t['label'], t['lo'], t['hi']) for t in tiers]}")
        return tiers

    except Exception as e:
        logger.error(f"Failed to compute budget tiers: {e}")
        _budget_tiers = _fallback_tiers()
        return _budget_tiers


def _fallback_tiers() -> list[dict]:
    """Fallback tiers when DB is unavailable."""
    return [
        {"label": "¥0 - ¥20", "lo": 0, "hi": 20},
        {"label": "¥20 - ¥50", "lo": 20, "hi": 50},
        {"label": "¥50 - ¥100", "lo": 50, "hi": 100},
        {"label": "¥100 - ¥200", "lo": 100, "hi": 200},
        {"label": "¥200+", "lo": 200, "hi": 999999},
    ]


def get_budget_options() -> list[str]:
    """Return budget tier labels for UI display (plain numbers, ¥ added by frontend)."""
    tiers = compute_budget_tiers()
    return [t["label"] for t in tiers]


def get_budget_range(label: str) -> tuple[int, int]:
    """Parse a budget label back to (lo, hi). Handles both '¥0 - ¥6' and '0 - 6' formats."""
    tiers = compute_budget_tiers()
    # Clean ¥ and spaces from label for matching
    clean = label.replace("¥", "").replace(" ", "")
    for t in tiers:
        t_clean = t["label"].replace("¥", "").replace(" ", "")
        if t_clean == clean:
            return t["lo"], t["hi"]
    return 0, 999999
