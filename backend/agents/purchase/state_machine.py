"""
State Machine — PurchaseAgent workflow states and transitions.

PurchaseStep enum defines the 4 states. Transition validation ensures
only valid moves are allowed.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class PurchaseStep(str, Enum):
    IDLE = "idle"              # no active workflow
    VIEWING = "viewing"        # viewing product details
    CONFIRMING = "confirming"  # awaiting confirmation (purchase/refund/cancel)
    PURCHASED = "purchased"    # purchase completed


# Allowed transitions: from → {to}
_TRANSITIONS: dict[PurchaseStep, set[PurchaseStep]] = {
    PurchaseStep.IDLE:       {PurchaseStep.VIEWING},
    PurchaseStep.VIEWING:    {PurchaseStep.CONFIRMING, PurchaseStep.IDLE},
    PurchaseStep.CONFIRMING: {PurchaseStep.PURCHASED, PurchaseStep.VIEWING},
    PurchaseStep.PURCHASED:  {PurchaseStep.IDLE},
}


def can_transition(current: PurchaseStep, target: PurchaseStep) -> bool:
    """Check if moving from current to target is allowed."""
    return target in _TRANSITIONS.get(current, set())


def validate_transition(current: PurchaseStep, target: PurchaseStep) -> None:
    """Raise ValueError if transition is not allowed."""
    if not can_transition(current, target):
        raise ValueError(
            f"Invalid transition: {current.value} → {target.value}"
        )


CONFIRM_TTL_SECONDS = 180  # 3 minutes


@dataclass
class PurchaseSessionState:
    """In-memory representation of the current purchase workflow state."""
    workflow_id: str = ""
    current_step: PurchaseStep = PurchaseStep.IDLE
    selected_product_id: int | None = None
    confirm_type: str | None = None        # "refund" | "cancel" | "purchase"
    confirm_token: str | None = None
    confirm_expires_at: str | None = None
    idempotency_key: str | None = None
    snapshot_hash: str | None = None

    def is_expired(self) -> bool:
        """Check if the confirm token has expired (3 min TTL for CONFIRMING)."""
        if not self.confirm_expires_at:
            return False
        from datetime import datetime
        try:
            at = datetime.fromisoformat(self.confirm_expires_at)
            return (datetime.utcnow() - at.replace(tzinfo=None)).total_seconds() > CONFIRM_TTL_SECONDS
        except (ValueError, TypeError):
            return False

    @classmethod
    def from_workflow(cls, wf) -> PurchaseSessionState:
        """Build from PurchaseWorkflow DB record."""
        from agents.models import PurchaseWorkflow
        return cls(
            workflow_id=wf.workflow_id,
            current_step=PurchaseStep(wf.current_step),
            selected_product_id=wf.selected_product_id,
            confirm_type=wf.confirm_type or None,
            confirm_token=wf.confirm_token or None,
            confirm_expires_at=wf.confirm_expires_at.isoformat() if wf.confirm_expires_at else None,
            idempotency_key=wf.idempotency_key or None,
            snapshot_hash=wf.snapshot_hash or None,
        )
