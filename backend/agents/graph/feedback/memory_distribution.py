"""
Memory Distribution — value_distribution with conflict resolution.

Replaces the naive "last value wins" approach from Phase A.
User preferences are stored as probability distributions, not single values.

Key behaviors:
  - Repeated confirmation → weight increases
  - Contradictory answer → both values coexist, with time decay
  - Gibberish answer → ignored
  - Auto-skip clarify when entropy < 0.2 and confirmed ≥ 2 times
"""

from __future__ import annotations
import json
import math
from datetime import datetime
from typing import Optional


# ── Entropy / Confidence ───────────────────────────────────────

def _entropy(weights: list[float]) -> float:
    """Shannon entropy of normalized weights.  Returns 0.0 if empty."""
    total = sum(weights)
    if total <= 0:
        return 0.0
    probs = [w / total for w in weights]
    return -sum(p * math.log2(p) for p in probs if p > 0)


def _max_entropy(n: int) -> float:
    """Maximum possible entropy for n values (uniform distribution)."""
    if n <= 1:
        return 0.0
    return math.log2(n)


def confidence_from_distribution(dist: dict[str, float]) -> float:
    """Confidence = 1 - normalized_entropy.  Higher = more certain."""
    if not dist:
        return 0.0
    n = len(dist)
    if n <= 1:
        return 1.0
    e = _entropy(list(dist.values()))
    max_e = _max_entropy(n)
    if max_e == 0:
        return 1.0
    return max(0.0, 1.0 - e / max_e)


# ── Distribution merge ──────────────────────────────────────────

def merge_preference(
    key: str,
    new_value: str,
    user_id: int,
    source: str = "clarify",
    source_confidence: float = 0.8,
) -> dict[str, float]:
    """Merge a new preference value into the user's distribution.

    Strategy:
      - If new_value matches an existing key → boost its weight (+0.3)
      - If new_value is new → add with initial weight 0.3
      - All weights decay by ×0.9 to give recency priority
      - Gibberish (too short / too long) → skip (return existing)

    Persists the merged distribution to UserPreference and returns it.
    """
    import django
    django.setup()
    from agents.models import UserPreference

    # ── Gibberish guard ──
    if len(new_value.strip()) < 1 or len(new_value) > 200:
        return _get_existing_distribution(key, user_id)

    # ── Load existing ──
    dist = _get_existing_distribution(key, user_id)

    # ── Decay all existing weights ──
    decayed = {v: w * 0.9 for v, w in dist.items()}

    # ── Merge new value ──
    if new_value in decayed:
        decayed[new_value] += 0.3  # boost existing
    else:
        decayed[new_value] = 0.3   # add new entry

    # ── Prune very weak entries ──
    pruned = {v: w for v, w in decayed.items() if w > 0.05}

    # ── Persist ──
    conf = confidence_from_distribution(pruned)
    UserPreference.objects.update_or_create(
        user_id=user_id,
        key=key,
        defaults={
            "value": json.dumps(pruned, ensure_ascii=False),
            "source_agent": source,
            "confidence": conf,
        },
    )

    return pruned


def get_distribution(user_id: int, key: str) -> dict[str, float]:
    """Get the current value distribution for a user preference key."""
    return _get_existing_distribution(key, user_id)


def should_clarify(user_id: int, key: str) -> bool:
    """Should we ask the user about this preference?

    Returns False (skip clarify) when:
      - Distribution entropy < 0.2 (very certain)
      - AND at least 2 entries exist (confirmed multiple times)
    """
    dist = _get_existing_distribution(key, user_id)
    if not dist:
        return True  # no data, must ask
    conf = confidence_from_distribution(dist)
    confirmed_count = len([v for v in dist.values() if v > 0.2])
    return not (conf > 0.8 and confirmed_count >= 2)


def get_best_value(user_id: int, key: str) -> Optional[str]:
    """Get the most likely value for a preference key."""
    dist = _get_existing_distribution(key, user_id)
    if not dist:
        return None
    return max(dist, key=dist.get)  # type: ignore


def get_all_preferences(user_id: int) -> dict[str, dict[str, float]]:
    """Get all preference distributions for a user.

    Returns: {key: {value: weight, ...}, ...}
    """
    import django
    django.setup()
    from agents.models import UserPreference

    prefs = UserPreference.objects.filter(user_id=user_id)
    result = {}
    for p in prefs:
        try:
            dist = json.loads(p.value)
            if isinstance(dist, dict):
                result[p.key] = dist
        except (json.JSONDecodeError, TypeError):
            # Legacy single-value: wrap in distribution
            result[p.key] = {p.value: p.confidence}
    return result


# ── Internal ────────────────────────────────────────────────────

def _get_existing_distribution(key: str, user_id: int) -> dict[str, float]:
    """Load distribution from UserPreference, or return empty dict."""
    import django
    django.setup()
    from agents.models import UserPreference

    try:
        pref = UserPreference.objects.get(user_id=user_id, key=key)
        dist = json.loads(pref.value)
        if isinstance(dist, dict):
            return {str(k): float(v) for k, v in dist.items()}
    except (UserPreference.DoesNotExist, json.JSONDecodeError, TypeError, ValueError):
        pass
    return {}
