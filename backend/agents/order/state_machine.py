"""
State Machine — OrderAgent workflow states and transitions.

OrderStep enum defines the 4 states. Transition validation ensures
only valid moves are allowed.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class OrderStep(str, Enum):
    IDLE = "idle"              # no active workflow
    LISTING = "listing"        # showing order list
    SELECTED = "selected"      # user picked one order
    CONFIRMING = "confirming"  # awaiting confirmation (refund/cancel)


# Allowed transitions: from → {to}
_TRANSITIONS: dict[OrderStep, set[OrderStep]] = {
    OrderStep.IDLE:       {OrderStep.LISTING},
    OrderStep.LISTING:    {OrderStep.SELECTED, OrderStep.IDLE},
    OrderStep.SELECTED:   {OrderStep.CONFIRMING, OrderStep.LISTING, OrderStep.IDLE},
    OrderStep.CONFIRMING: {OrderStep.SELECTED, OrderStep.IDLE},
}


def can_transition(current: OrderStep, target: OrderStep) -> bool:
    """Check if moving from current to target is allowed."""
    return target in _TRANSITIONS.get(current, set())


def validate_transition(current: OrderStep, target: OrderStep) -> None:
    """Raise ValueError if transition is not allowed."""
    if not can_transition(current, target):
        raise ValueError(
            f"Invalid transition: {current.value} → {target.value}"
        )


@dataclass
class OrderSessionState:
    """In-memory representation of the current workflow state."""
    workflow_id: str = ""
    current_step: OrderStep = OrderStep.IDLE
    selected_order_id: int | None = None
    confirm_type: str | None = None           # "refund" | "cancel"
    confirm_token: str | None = None
    confirm_expires_at: str | None = None
    idempotency_key: str | None = None
    orders_snapshot: list[dict] = field(default_factory=list)
    snapshot_hash: str | None = None
    snapshot_at: str | None = None

    def is_expired(self) -> bool:
        """Check if snapshot has expired (10 min TTL for listing)."""
        if not self.snapshot_at:
            return False
        from datetime import datetime, timedelta
        try:
            at = datetime.fromisoformat(self.snapshot_at)
            return (datetime.utcnow() - at).total_seconds() > 600
        except (ValueError, TypeError):
            return False

    @classmethod
    def from_workflow(cls, wf) -> OrderSessionState:
        """Build from OrderWorkflow DB record."""
        from agents.models import OrderWorkflow
        return cls(
            workflow_id=wf.workflow_id,
            current_step=OrderStep(wf.current_step),
            selected_order_id=wf.selected_order_id,
            confirm_type=wf.confirm_type,
            confirm_token=wf.confirm_token,
            confirm_expires_at=wf.confirm_expires_at.isoformat() if wf.confirm_expires_at else None,
            idempotency_key=wf.idempotency_key,
            orders_snapshot=wf.orders_snapshot or [],
            snapshot_hash=wf.snapshot_hash,
            snapshot_at=wf.snapshot_at.isoformat() if wf.snapshot_at else None,
        )
