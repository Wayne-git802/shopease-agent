"""
Signal Classifier — raw event → SignalType classification.

This is the entry point of the Signal Standardization Layer (B-0).
Every raw user behavior event passes through here before flowing to
any downstream consumer (ranking, memory, routing).
"""

from __future__ import annotations
from typing import Optional

from agents.graph.contracts.signal_contract import SignalType, SIGNAL_WEIGHTS

# ── Classification mapping ─────────────────────────────────────────

_EVENT_TYPE_MAP: dict[str, SignalType] = {
    "click":          SignalType.EXPLORATION,
    "dwell":          SignalType.EXPLORATION,
    "add_cart":       SignalType.INTENT,
    "purchase":       SignalType.CONVERSION,
    "dismiss":        SignalType.NEGATIVE,
    "skip":           SignalType.NEGATIVE,
    "clarify_answer": SignalType.STATED,
    "clarify":        SignalType.STATED,
}


def classify(event: dict) -> tuple[SignalType, float]:
    """Classify a raw event dict into (SignalType, weight).

    Args:
        event: dict with at minimum an 'event_type' key.
               Optional: 'product_id', 'category', 'session_id', 'metadata'.

    Returns:
        (SignalType, weight) — the weight is looked up from SIGNAL_WEIGHTS.
    """
    event_type = (event.get("event_type") or "").lower()
    signal_type = _EVENT_TYPE_MAP.get(event_type, SignalType.EXPLORATION)
    weight = SIGNAL_WEIGHTS.get(signal_type, 0.0)
    return signal_type, weight


def classify_and_create(
    event: dict,
    user_id: Optional[int] = None,
) -> tuple[SignalType, float]:
    """Classify event and persist a StandardizedSignal record.

    Args:
        event: raw event dict (must contain 'event_type', optionally
               'session_id', 'product_id', 'category', 'metadata').
        user_id: the authenticated user id (can be None for guests).

    Returns:
        (SignalType, weight) of the classified signal.
    """
    signal_type, weight = classify(event)

    try:
        import django
        django.setup()
        from agents.models import StandardizedSignal

        StandardizedSignal.objects.create(
            session_id=event.get("session_id", ""),
            user_id=user_id,
            signal_type=signal_type.value,
            product_id=event.get("product_id"),
            category=event.get("category", ""),
            value=weight,
            metadata=event.get("metadata", {}),
        )
    except Exception:
        # Signal persistence is non-critical — don't break the request
        pass

    return signal_type, weight
