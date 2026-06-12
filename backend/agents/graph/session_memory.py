"""
Session Memory — DB-backed short-term state for multi-turn conversations.

When the graph asks a clarifying question, it stores the pending state here.
On the next invocation, entry_router and search_node recover context from
this store instead of re-classifying or restarting.

Lifecycle:
  - Created by orchestrator after response_node returns a clarify_block
  - Consumed by entry_router (skip intent classification) + search_node (enrich)
  - Cleared after a successful (non-clarify) response, or after TTL expires

Storage: Django DB (was in-process dict).  Survives process restarts and
works across multiple workers.  Expired rows lazily cleaned on read.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from django.utils import timezone as django_timezone
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TTL_SECONDS = 300   # 5 minutes — clarify chains are short-lived


class SessionMemory(BaseModel):
    """In-memory representation.  Persisted via SessionState model."""
    session_id: str
    pending_intent: str = ""
    collected_slots: dict[str, str] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > TTL_SECONDS


# ═══════════════════════════════════════════════════════════════
# DB helpers
# ═══════════════════════════════════════════════════════════════

def _row_to_session_memory(row) -> SessionMemory:
    """Convert a SessionState DB row to a SessionMemory pydantic model."""
    return SessionMemory(
        session_id=row.session_id,
        pending_intent=row.pending_intent,
        collected_slots=row.collected_slots or {},
        missing_slots=row.missing_slots or [],
        created_at=row.created_at.timestamp(),
    )


def _now() -> datetime:
    return django_timezone.now()


def _get_row(session_id: str):
    """Fetch a non-expired SessionState row, or None."""
    from agents.models import SessionState

    try:
        row = SessionState.objects.filter(session_id=session_id).first()
    except Exception:
        logger.warning("SessionState query failed for session=%s", session_id, exc_info=True)
        return None

    if row is None:
        return None

    if row.expires_at < _now():
        # Lazy cleanup — expired
        try:
            row.delete()
        except Exception:
            logger.warning("SessionState lazy delete failed for session=%s", session_id, exc_info=True)
        return None

    return row


# ═══════════════════════════════════════════════════════════════
# Public API (unchanged signatures)
# ═══════════════════════════════════════════════════════════════

def get(session_id: str) -> SessionMemory | None:
    """Retrieve and validate session memory. Returns None if expired or missing."""
    row = _get_row(session_id)
    if row is None:
        return None
    return _row_to_session_memory(row)


def put(mem: SessionMemory) -> None:
    """Store or update session memory."""
    from agents.models import SessionState

    try:
        SessionState.objects.update_or_create(
            session_id=mem.session_id,
            defaults={
                "pending_intent": mem.pending_intent,
                "collected_slots": mem.collected_slots,
                "missing_slots": mem.missing_slots,
                "expires_at": _now() + timedelta(seconds=TTL_SECONDS),
            },
        )
    except Exception:
        logger.warning("SessionState put failed for session=%s", mem.session_id, exc_info=True)


def clear(session_id: str) -> None:
    """Remove session memory after a successful resolution."""
    from agents.models import SessionState

    try:
        SessionState.objects.filter(session_id=session_id).delete()
    except Exception:
        logger.warning("SessionState clear failed for session=%s", session_id, exc_info=True)


def collect_answer(session_id: str, slot_key: str, value: str) -> None:
    """Record a user's answer for a pending slot."""
    mem = get(session_id)
    if mem is None:
        return
    mem.collected_slots[slot_key] = value
    if slot_key in mem.missing_slots:
        mem.missing_slots.remove(slot_key)
    put(mem)


def cleanup_expired() -> int:
    """Remove all expired entries. Returns count removed."""
    from agents.models import SessionState

    try:
        count, _ = SessionState.objects.filter(expires_at__lt=_now()).delete()
        return count
    except Exception:
        logger.warning("SessionState cleanup failed", exc_info=True)
        return 0


# ═══════════════════════════════════════════════════════════════
# ConversationState — also DB-backed now
# ═══════════════════════════════════════════════════════════════

from .preprocessor import ConversationState, DialogueContext, PendingReference, ClarificationReason


def _row_to_conv_state(row) -> ConversationState:
    """Convert a SessionState DB row to a ConversationState dataclass."""
    pending_ref = None
    if row.pending_reference:
        try:
            pending_ref = PendingReference(
                product_id=row.pending_reference["product_id"],
                product_name=row.pending_reference["product_name"],
                waiting_for=ClarificationReason(row.pending_reference["waiting_for"]),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Failed to deserialize pending_reference for session=%s", row.session_id)

    return ConversationState(
        session_id=row.session_id,
        last_intent=row.last_intent,
        pending_action_type=row.pending_action_type,
        pending_question=row.pending_question,
        pending_options=row.pending_options or {},
        original_query=row.original_query,
        context_summary=row.context_summary,
        created_at=row.created_at.timestamp(),
        dialogue=DialogueContext(
            injected_slot=row.injected_slot,
            last_user_query=row.last_user_query,
            expects_followup=row.expects_followup,
        ),
        pending_reference=pending_ref,
    )


def get_conv_state(session_id: str) -> ConversationState | None:
    """Retrieve conversation state for the preprocessor."""
    if not session_id:
        return None
    row = _get_row(session_id)
    if row is None:
        return None
    return _row_to_conv_state(row)


def put_conv_state(cs: ConversationState) -> None:
    """Store or update conversation state."""
    from agents.models import SessionState

    pending_ref_dict = None
    if cs.pending_reference is not None:
        pending_ref_dict = {
            "product_id": cs.pending_reference.product_id,
            "product_name": cs.pending_reference.product_name,
            "waiting_for": cs.pending_reference.waiting_for.value,
        }

    try:
        SessionState.objects.update_or_create(
            session_id=cs.session_id,
            defaults={
                "last_intent": cs.last_intent,
                "pending_action_type": cs.pending_action_type,
                "pending_question": cs.pending_question,
                "pending_options": cs.pending_options,
                "original_query": cs.original_query,
                "context_summary": cs.context_summary,
                "injected_slot": cs.dialogue.injected_slot or "",
                "last_user_query": cs.dialogue.last_user_query,
                "expects_followup": cs.dialogue.expects_followup,
                "pending_reference": pending_ref_dict,
                "expires_at": _now() + timedelta(seconds=TTL_SECONDS),
            },
        )
    except Exception:
        logger.warning("ConversationState put failed for session=%s", cs.session_id, exc_info=True)


def clear_conv_state(session_id: str) -> None:
    """Remove conversation state."""
    clear(session_id)  # same row
