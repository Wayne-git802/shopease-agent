"""
DecisionTrace — structured decision record for execution replay.

Captures every meaningful decision made inside the graph execution:
  - What plan was validated
  - Which validation corrections were applied
  - Which node branch was taken (and why)
  - Signal state snapshot at decision time
  - Fallback chain details

A DecisionTrace anchors a single user request to an explainable,
replayable execution path.  Paired with SessionTrace for the full
observability picture.

Schema is designed to be persisted as JSON in SessionTrace.decision_trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal


# ═══════════════════════════════════════════════════════════════
# Sub-records
# ═══════════════════════════════════════════════════════════════

@dataclass
class SignalSnapshot:
    """Signal state at decision time — for drift detection."""
    total_signals: int = 0
    active_signals: int = 0          # signals within time window
    top_categories: dict[str, float] = field(default_factory=dict)
    window_days: int = 90

    def to_dict(self) -> dict:
        return {
            "total_signals": self.total_signals,
            "active_signals": self.active_signals,
            "top_categories": self.top_categories,
            "window_days": self.window_days,
        }


@dataclass
class BranchDecision:
    """Which branch a node took and why."""
    node: str                       # "search" | "recommend" | "merge"
    branch: str                     # e.g. "structured_sort" | "semantic" | "for-you"
    reason: str                     # human-readable
    inputs: dict = field(default_factory=dict)  # key inputs that drove decision

    def to_dict(self) -> dict:
        return {
            "node": self.node,
            "branch": self.branch,
            "reason": self.reason,
            "inputs": self.inputs,
        }


@dataclass
class FallbackStep:
    """One step in a fallback chain."""
    step: int                       # 0 = primary, 1 = secondary, 2 = tertiary
    strategy: str                   # e.g. "cf", "embedding", "popular"
    triggered: bool                 # whether this step was attempted
    reason: str = ""                # why triggered (or why skipped)
    result_count: int = 0           # items returned
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "strategy": self.strategy,
            "triggered": self.triggered,
            "reason": self.reason,
            "result_count": self.result_count,
            "latency_ms": self.latency_ms,
        }


# ═══════════════════════════════════════════════════════════════
# DecisionTrace
# ═══════════════════════════════════════════════════════════════

@dataclass
class DecisionTrace:
    """Full decision trace for one graph execution."""

    session_id: str = ""
    query: str = ""

    # ── Plan lifecycle ──
    plan_version: str = ""                  # "v2" — which ConstraintParser version
    plan_raw: dict = field(default_factory=dict)      # original SearchPlan.to_dict()
    plan_validated: dict = field(default_factory=dict) # after ExecutionValidator
    validation_decisions: list[dict] = field(default_factory=list)
    plan_downgraded: bool = False

    # ── Node branches ──
    node_decisions: list[BranchDecision] = field(default_factory=list)

    # ── Signal state ──
    signal_snapshot: SignalSnapshot = field(default_factory=SignalSnapshot)

    # ── Fallback chain ──
    fallback_chain: list[FallbackStep] = field(default_factory=list)
    fallback_triggered: bool = False

    # ── Metadata ──
    recorded_at: str = ""                   # ISO timestamp
    validator_version: str = "v1"

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "plan_version": self.plan_version,
            "plan_raw": self.plan_raw,
            "plan_validated": self.plan_validated,
            "validation_decisions": self.validation_decisions,
            "plan_downgraded": self.plan_downgraded,
            "node_decisions": [nd.to_dict() for nd in self.node_decisions],
            "signal_snapshot": self.signal_snapshot.to_dict(),
            "fallback_chain": [fs.to_dict() for fs in self.fallback_chain],
            "fallback_triggered": self.fallback_triggered,
            "recorded_at": self.recorded_at,
            "validator_version": self.validator_version,
        }


# ═══════════════════════════════════════════════════════════════
# Factory — build trace from execution context
# ═══════════════════════════════════════════════════════════════

def build_trace(
    session_id: str,
    query: str,
    plan_dict: dict,
    validated: "ValidatedPlan",       # from execution_validator
    node_branches: list[BranchDecision],
    signal_snapshot: SignalSnapshot,
    fallback_chain: list[FallbackStep] | None = None,
) -> DecisionTrace:
    """Build a DecisionTrace from current execution context."""
    from datetime import datetime as dt_dt, timezone

    return DecisionTrace(
        session_id=session_id,
        query=query,
        plan_version="v2",
        plan_raw=plan_dict,
        plan_validated=validated.to_dict(),
        validation_decisions=[d.to_dict() for d in validated.decisions],
        plan_downgraded=validated.downgraded,
        node_decisions=node_branches,
        signal_snapshot=signal_snapshot,
        fallback_chain=fallback_chain or [],
        fallback_triggered=bool(fallback_chain and any(f.triggered for f in fallback_chain)),
        recorded_at=dt_dt.now(timezone.utc).isoformat(),
        validator_version="v1",
    )


# ═══════════════════════════════════════════════════════════════
# Snapshot helpers
# ═══════════════════════════════════════════════════════════════

def snapshot_signals(user_id: int | None = None, window_days: int = 90) -> SignalSnapshot:
    """Capture current signal state for trace."""
    if not user_id:
        return SignalSnapshot()

    total = 0
    active = 0
    top_categories: dict[str, float] = {}

    try:
        from .feedback.signal_store import get_user_signals, signal_count
        import django
        django.setup()
        from django.utils import timezone as dj_timezone

        total = signal_count(user_id)
        top_categories = get_user_signals(user_id)

        # Count active (within window)
        from .feedback.signal_store import _decay_weight
        from agents.models import StandardizedSignal
        from agents.graph.contracts.signal_contract import SignalType
        from datetime import timedelta

        now = dj_timezone.now()
        cutoff = now - timedelta(days=window_days)
        active = StandardizedSignal.objects.filter(
            user_id=user_id,
            signal_type__in=[st.value for st in (SignalType.INTENT, SignalType.CONVERSION)],
            created_at__gte=cutoff,
        ).count()
    except Exception:
        pass

    return SignalSnapshot(
        total_signals=total,
        active_signals=active,
        top_categories=top_categories,
        window_days=window_days,
    )
