"""
Workflow Store — persist/load OrderAgent workflow state.

TTL rules:
  listing + snapshot → 10min
  selected_order     → 5min
  pending_confirmation → 3min
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from django.utils import timezone as dj_timezone

from agents.models import OrderWorkflow

# ═══════════════════════════════════════════════════════════
# TTL config
# ═══════════════════════════════════════════════════════════

TTL_MINUTES = {
    "listing": 10,
    "selected": 5,
    "confirming": 3,
    "idle": 30,  # keep idle workflows for recovery
}


def _ttl_for_step(step: str) -> int:
    return TTL_MINUTES.get(step, 10)


def _is_expired(wf: OrderWorkflow) -> bool:
    """Check if workflow has exceeded its step-specific TTL."""
    ttl = _ttl_for_step(wf.current_step)
    expiry = wf.updated_at + timedelta(minutes=ttl)
    return dj_timezone.now() > expiry


# ═══════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════

def load(session_id: str) -> OrderWorkflow | None:
    """Load the active workflow for a session. Returns None if expired/missing."""
    try:
        wf = OrderWorkflow.objects.filter(session_id=session_id).latest("updated_at")
    except OrderWorkflow.DoesNotExist:
        return None

    if _is_expired(wf):
        # Expired — delete and return None
        wf.delete()
        return None

    return wf


def save(
    session_id: str,
    user_id: int | None,
    current_step: str,
    selected_order_id: int | None = None,
    confirm_type: str | None = None,
    confirm_token: str | None = None,
    confirm_expires_at: datetime | None = None,
    idempotency_key: str | None = None,
    orders_snapshot: list | None = None,
    snapshot_hash: str | None = None,
    workflow_id: str | None = None,
) -> OrderWorkflow:
    """Create or update a workflow record."""
    now = dj_timezone.now()

    if workflow_id:
        wf, _ = OrderWorkflow.objects.get_or_create(
            workflow_id=workflow_id,
            defaults={
                "session_id": session_id,
                "user_id": user_id,
            },
        )
    else:
        wf = OrderWorkflow(
            workflow_id=f"wf_{uuid.uuid4().hex[:16]}",
            session_id=session_id,
            user_id=user_id,
        )

    wf.current_step = current_step
    wf.selected_order_id = selected_order_id
    wf.confirm_type = confirm_type
    wf.confirm_token = confirm_token
    wf.confirm_expires_at = confirm_expires_at
    wf.idempotency_key = idempotency_key
    if orders_snapshot is not None:
        wf.orders_snapshot = orders_snapshot
        wf.snapshot_at = now
    if snapshot_hash is not None:
        wf.snapshot_hash = snapshot_hash
    wf.save()
    return wf


def delete(session_id: str) -> bool:
    """Delete workflow for a session."""
    count, _ = OrderWorkflow.objects.filter(session_id=session_id).delete()
    return count > 0


def clear_expired() -> int:
    """Remove all expired workflows. Returns count deleted."""
    deleted = 0
    for wf in OrderWorkflow.objects.all():
        if _is_expired(wf):
            wf.delete()
            deleted += 1
    return deleted
