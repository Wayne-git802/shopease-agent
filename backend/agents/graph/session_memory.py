"""
Session Memory — in-process short-term memory for multi-turn clarification.

When the graph asks a clarifying question, it stores the pending state here.
On the next invocation, entry_router and recommend_node recover context from
this store instead of re-classifying or restarting.

Lifecycle:
  - Created by orchestrator after response_node returns a clarify_block
  - Consumed by entry_router (skip intent classification) + recommend_node (enrich)
  - Cleared after a successful (non-clarify) response, or after TTL expires

Storage: in-process dict (fast, zero-dependency).  Restart-safe enough because
clarify conversations are < 30 seconds.  Future: swap to SQLite via same interface.
"""

import time
from datetime import datetime, timezone
from pydantic import BaseModel, Field

TTL_SECONDS = 300   # 5 minutes — clarify chains are short-lived


class SessionMemory(BaseModel):
    session_id: str
    pending_intent: str = ""            # The intent being pursued (e.g. "recommend")
    collected_slots: dict[str, str] = Field(default_factory=dict)
    missing_slots: list[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > TTL_SECONDS


# ── In-process store ──────────────────────────────────────────────

_store: dict[str, SessionMemory] = {}


def get(session_id: str) -> SessionMemory | None:
    """Retrieve and validate session memory. Returns None if expired or missing."""
    mem = _store.get(session_id)
    if mem is None:
        return None
    if mem.expired:
        # Soft reset: clear pending state, keep active_domain for continuity
        mem.pending_intent = ""
        mem.collected_slots = {}
        mem.missing_slots = []
        mem.created_at = time.time()
        return None
    return mem


def put(mem: SessionMemory) -> None:
    """Store or update session memory."""
    _store[mem.session_id] = mem


def clear(session_id: str) -> None:
    """Remove session memory after a successful resolution."""
    _store.pop(session_id, None)


def collect_answer(session_id: str, slot_key: str, value: str) -> None:
    """Record a user's answer for a pending slot."""
    mem = get(session_id)
    if mem is None:
        return
    mem.collected_slots[slot_key] = value
    # Remove from missing
    if slot_key in mem.missing_slots:
        mem.missing_slots.remove(slot_key)
    put(mem)


def cleanup_expired() -> int:
    """Remove all expired entries. Returns count removed."""
    now = time.time()
    expired = [sid for sid, m in _store.items() if (now - m.created_at) > TTL_SECONDS]
    for sid in expired:
        del _store[sid]
    return len(expired)


# ═══════════════════════════════════════════════════════════════
# ConversationState — deterministic session state for preprocessor
# ═══════════════════════════════════════════════════════════════

_conv_store: dict[str, "ConversationState"] = {}

# Import here to avoid circular dependency
from .preprocessor import ConversationState


def get_conv_state(session_id: str) -> ConversationState | None:
    """Retrieve conversation state for the preprocessor."""
    if not session_id:
        return None
    cs = _conv_store.get(session_id)
    if cs is None:
        return None
    # Same TTL as SessionMemory
    if (time.time() - cs.created_at) > TTL_SECONDS:
        del _conv_store[session_id]
        return None
    return cs


def put_conv_state(cs: ConversationState) -> None:
    """Store or update conversation state."""
    cs.created_at = time.time()
    _conv_store[cs.session_id] = cs


def clear_conv_state(session_id: str) -> None:
    """Remove conversation state."""
    _conv_store.pop(session_id, None)
