"""
Signal Store — accumulate StandardizedSignals per (user, category) with decay.

Reads from the StandardizedSignal table, groups by user + category,
applies exponential time decay (τ=90 days), and returns accumulated scores.

Only INTENT and CONVERSION signals contribute to ranking weight.
EXPLORATION and STATED are excluded (they go to diversity and memory respectively).
"""

from __future__ import annotations
import math
from datetime import datetime, timedelta
from collections import defaultdict

from agents.graph.contracts.signal_contract import SignalType

# ── Config ──────────────────────────────────────────────────────

TAU = 90 * 86400   # 90 days in seconds
RANKING_SIGNAL_TYPES = {SignalType.INTENT, SignalType.CONVERSION}


def _decay_weight(created_at: datetime, now: datetime | None = None) -> float:
    """Exponential decay: exp(-Δt / τ)."""
    from datetime import timezone as dt_utc
    from django.utils import timezone as dj_timezone
    if now is None:
        now = dj_timezone.now()
    # Normalize both to UTC for comparison
    if dj_timezone.is_aware(created_at):
        created_at = created_at.astimezone(dt_utc.utc)
    if dj_timezone.is_aware(now):
        now = now.astimezone(dt_utc.utc)
    delta = (now - created_at).total_seconds()
    if delta < 0:
        return 1.0
    return math.exp(-delta / TAU)


# ── Public API ──────────────────────────────────────────────────

def get_user_signals(user_id: int) -> dict[str, float]:
    """Return accumulated decayed signal weights per category for a user.

    Returns:
        {category_name: total_weight} — e.g. {"Gaming Headsets": 0.15, "Watches": 0.04}

    Only INTENT and CONVERSION signals are included.
    Each signal's value × decay_weight is summed per category.
    """
    import django
    django.setup()
    from django.utils import timezone as dj_timezone
    from agents.models import StandardizedSignal

    now = dj_timezone.now()
    cutoff = now - timedelta(days=180)  # don't bother decaying signals older than 180d

    signals = StandardizedSignal.objects.filter(
        user_id=user_id,
        signal_type__in=[st.value for st in RANKING_SIGNAL_TYPES],
        created_at__gte=cutoff,
    ).values_list("category", "value", "created_at")

    accum: dict[str, float] = defaultdict(float)
    for category, value, created_at in signals:
        if not category:
            continue
        dw = _decay_weight(created_at, now)
        accum[category] += value * dw

    return dict(accum)


def get_category_signal(user_id: int, category: str) -> float:
    """Get the accumulated signal weight for a specific category."""
    signals = get_user_signals(user_id)
    return signals.get(category, 0.0)


def signal_count(user_id: int) -> int:
    """How many INTENT+CONVERSION signals does this user have?"""
    import django
    django.setup()
    from agents.models import StandardizedSignal
    return StandardizedSignal.objects.filter(
        user_id=user_id,
        signal_type__in=[st.value for st in RANKING_SIGNAL_TYPES],
    ).count()
