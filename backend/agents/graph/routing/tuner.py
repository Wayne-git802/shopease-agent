"""
Routing Tuner — online threshold optimization for entry_router.

Implements the Phase B-3 closed loop:
  1. Record every routing decision with its outcome
  2. Calculate multivariate reward (not naive click=correct)
  3. Adjust FAST_CONFIDENCE_THRESHOLD within safety bounds

Safety bounds:
  - Threshold never below 0.55 (minimum fast-routing capability)
  - Threshold never above 0.90 (always leave 10% for LLM fallback)
  - Step size: 0.03 per adjustment
  - Rolling window: last 200 routing events
"""

from __future__ import annotations

# ── Config ──────────────────────────────────────────────────────

DEFAULT_THRESHOLD = 0.85
THRESHOLD_MIN = 0.55
THRESHOLD_MAX = 0.90
THRESHOLD_STEP = 0.03
ROLLING_WINDOW = 200
TARGET_ACCURACY_LOW = 0.50   # below → lower threshold (more LLM)
TARGET_ACCURACY_HIGH = 0.80  # above → raise threshold (more fast path)

# ── Reward calculator ───────────────────────────────────────────

def routing_reward(events: list[dict]) -> float:
    """Multivariate reward: NOT just click=correct.

    Weights reflect how strongly each outcome validates the routing:
      - conversion (purchase) → +0.50 (route was likely correct)
      - intent (add_cart)     → +0.20 (route was probably correct)
      - exploration (click)   → +0.02 (weak signal only)
      - negative (dismiss)    → -0.05 (mild penalty)
      - requery (bounce)      → -0.15 (route was likely wrong)

    Returns clipped to [-1.0, 1.0].
    """
    reward = 0.0
    for e in events:
        outcome = (e.get("outcome") or "").lower()
        if outcome == "purchased":
            reward += 0.50
        elif outcome == "clicked":
            reward += 0.02
        elif outcome in ("dismissed", "ignored"):
            reward -= 0.05
        elif outcome == "requeried":
            reward -= 0.15
        # add_cart is tracked via StandardizedSignal INTENT type
        # but outcome_type doesn't have a direct "added_to_cart" yet
    return max(-1.0, min(1.0, reward))


# ── Threshold adaptation ─────────────────────────────────────────

# Module-level mutable threshold (persisted via RoutingTuningLog for replay)
_current_threshold = DEFAULT_THRESHOLD


def get_threshold() -> float:
    """Return the current dynamically-tuned confidence threshold."""
    return _current_threshold


def record_routing(
    session_id: str,
    intent: str,
    fast_confidence: float,
    routing_method: str,
) -> None:
    """Record a routing decision.  Outcome is filled later via update_outcome."""
    import django
    django.setup()
    from agents.models import RoutingTuningLog

    RoutingTuningLog.objects.create(
        session_id=session_id,
        intent=intent,
        fast_confidence=fast_confidence,
        routing_method=routing_method,
        threshold_used=_current_threshold,
        outcome="unknown",
        reward_score=0.0,
    )


def update_outcome(session_id: str, outcome: str) -> None:
    """Update the outcome of a routing decision and recalculate reward.

    Called when we learn what happened (clicked, purchased, dismissed, requery).
    """
    import django
    django.setup()
    from agents.models import RoutingTuningLog

    log = RoutingTuningLog.objects.filter(session_id=session_id).order_by('-created_at').first()
    if not log:
        return

    log.outcome = outcome
    log.reward_score = routing_reward([{"outcome": outcome}])
    log.save(update_fields=["outcome", "reward_score"])

    _maybe_adjust_threshold()


def requery_detected(session_id: str) -> None:
    """Shortcut: user re-queried → likely routing failure."""
    update_outcome(session_id, "requeried")


# ── Internal: threshold adjustment ──────────────────────────────

def _maybe_adjust_threshold() -> None:
    """Check rolling window accuracy and adjust threshold if needed."""
    global _current_threshold

    import django
    django.setup()
    from agents.models import RoutingTuningLog

    recent = RoutingTuningLog.objects.order_by('-created_at')[:ROLLING_WINDOW]
    total = recent.count()
    if total < 50:
        return  # not enough data

    # "Successful" = reward > 0.3 (strong positive signal)
    successful = sum(1 for r in recent if r.reward_score > 0.3)
    accuracy = successful / total

    old = _current_threshold
    if accuracy < TARGET_ACCURACY_LOW:
        _current_threshold = max(THRESHOLD_MIN, old - THRESHOLD_STEP)
    elif accuracy > TARGET_ACCURACY_HIGH:
        _current_threshold = min(THRESHOLD_MAX, old + THRESHOLD_STEP)

    if _current_threshold != old:
        _log_threshold_change(old, _current_threshold, accuracy, total)


def _log_threshold_change(old: float, new: float, accuracy: float, total: int) -> None:
    """Persist threshold change as a RoutingTuningLog with special outcome."""
    import django
    django.setup()
    from agents.models import RoutingTuningLog
    RoutingTuningLog.objects.create(
        session_id=f"__tuner__{total}",
        intent="__threshold__",
        fast_confidence=accuracy,
        routing_method="tuner",
        threshold_used=new,
        outcome=f"{old:.2f}->{new:.2f}",
        reward_score=accuracy,
    )
