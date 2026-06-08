"""
Workflow Store — CRUD for PurchaseWorkflow DB persistence.

Provides load/save/delete for PurchaseSessionState backed by the
PurchaseWorkflow Django model.
"""

from __future__ import annotations

from agents.models import PurchaseWorkflow
from .state_machine import PurchaseSessionState, PurchaseStep


def load(session_id: str) -> PurchaseSessionState | None:
    """Read workflow from DB and hydrate into PurchaseSessionState.

    Returns None if no workflow record exists for the session.
    """
    wf = PurchaseWorkflow.objects.filter(session_id=session_id).first()
    if wf is None:
        return None
    return PurchaseSessionState.from_workflow(wf)


def save(session_id: str, state: PurchaseSessionState) -> None:
    """Persist workflow state to DB via update_or_create."""
    wf, _created = PurchaseWorkflow.objects.update_or_create(
        session_id=session_id,
        defaults={
            "workflow_id": state.workflow_id,
            "current_step": state.current_step.value,
            "selected_product_id": state.selected_product_id,
            "confirm_type": state.confirm_type or "",
            "confirm_token": state.confirm_token or "",
            "confirm_expires_at": _parse_datetime(state.confirm_expires_at),
            "idempotency_key": state.idempotency_key or "",
            "snapshot_hash": state.snapshot_hash or "",
        },
    )


def delete(session_id: str) -> None:
    """Remove the workflow record for a session."""
    PurchaseWorkflow.objects.filter(session_id=session_id).delete()


def _parse_datetime(iso_str: str | None):
    """Parse an ISO datetime string to a datetime object, or None."""
    if not iso_str:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None
