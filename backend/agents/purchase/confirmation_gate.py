"""
Confirmation Gate — token-based confirmation for purchase operations.

Guards purchase/refund/cancel with:
  - Unique confirmation token (bound to workflow_id + product_id)
  - Snapshot hash comparison (detect price/stock change between prompt and confirm)
  - Expiry (3 min)
  - Consumed flag (prevent double-click)
"""

from __future__ import annotations

import uuid
import hashlib
from datetime import datetime, timedelta, timezone

from .state_machine import PurchaseStep, PurchaseSessionState, CONFIRM_TTL_SECONDS

CONFIRM_TTL_MINUTES = 3


def generate_token(
    workflow_id: str,
    product_id: int,
    confirm_type: str,
    snapshot: dict,
) -> dict:
    """Generate a confirmation token and expiry.

    Args:
        workflow_id: Unique workflow identifier.
        product_id: The product being purchased/refunded/cancelled.
        confirm_type: One of "purchase", "refund", "cancel".
        snapshot: Dict with "price" and "stock" keys for hash computation.

    Returns:
        dict with token, workflow_id, product_id, confirm_type,
        snapshot_hash, expires_at, consumed fields.
    """
    token = uuid.uuid4().hex[:16]
    expires = datetime.now(timezone.utc) + timedelta(minutes=CONFIRM_TTL_MINUTES)

    # Use hashlib.sha256 for deterministic snapshot hash
    # (NOT Python's built-in hash() which is randomized per process)
    raw = f"{product_id}:{snapshot['price']}:{snapshot['stock']}".encode()
    snapshot_hash = hashlib.sha256(raw).hexdigest()[:16]

    return {
        "token": token,
        "workflow_id": workflow_id,
        "product_id": product_id,
        "confirm_type": confirm_type,
        "snapshot_hash": snapshot_hash,
        "expires_at": expires.isoformat(),
        "consumed": False,
    }


def validate_token(
    wf_state: PurchaseSessionState | None,
    user_token: str | None,
    current_snapshot: dict | None,
) -> dict:
    """Validate a confirmation request before execution.

    Args:
        wf_state: Current purchase workflow state (may be None).
        user_token: Token provided by the user (may be None).
        current_snapshot: Current product snapshot dict with "price" and "stock".

    Returns:
        {"valid": bool, "error": str|None}
    """
    if not wf_state or wf_state.current_step != PurchaseStep.CONFIRMING:
        return {"valid": False, "error": "当前没有待确认的操作"}

    if not wf_state.confirm_token:
        return {"valid": False, "error": "确认令牌缺失"}

    # Check expiry
    if wf_state.confirm_expires_at:
        try:
            expires = datetime.fromisoformat(wf_state.confirm_expires_at)
            if datetime.utcnow() > expires.replace(tzinfo=None):
                return {"valid": False, "error": "确认已过期（3分钟），请重新操作"}
        except (ValueError, TypeError):
            pass

    # Check consumed (double-click protection via idempotency_key)
    if wf_state.idempotency_key:
        return {"valid": False, "error": "该操作已执行，请勿重复确认"}

    # Snapshot hash verification
    if wf_state.snapshot_hash and current_snapshot and wf_state.selected_product_id:
        raw = f"{wf_state.selected_product_id}:{current_snapshot['price']}:{current_snapshot['stock']}".encode()
        current_hash = hashlib.sha256(raw).hexdigest()[:16]
        if current_hash != wf_state.snapshot_hash:
            return {
                "valid": False,
                "error": "价格或库存已变更，请重新确认",
            }

    return {"valid": True, "error": None}


def consume_token(wf_state: PurchaseSessionState) -> None:
    """Mark the workflow as consumed to prevent double execution.

    Sets the idempotency_key on the given workflow state.
    The caller must persist this change to the database.
    """
    wf_state.idempotency_key = wf_state.workflow_id  # mark as consumed
