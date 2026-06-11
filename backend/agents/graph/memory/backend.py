"""
MemoryBackend — pluggable storage backend for AgentMemory.

Protocol: MemoryBackend — swap implementations without touching agents.
DefaultMemoryBackend — production backend wrapping existing DB modules.
"""

from __future__ import annotations
from typing import Protocol, Any


class MemoryBackend(Protocol):
    """Pluggable memory backend. Implementations are stateless function wrappers."""

    def load_workflow_item(self, session_id: str, agent_type: str) -> Any: ...
    def recall_session(self, session_id: str) -> Any: ...
    def save_session(self, session_id: str, **kwargs) -> None: ...
    def recall_user(self, user_id: int) -> Any: ...
    def recall_shared_view(self, session_id: str) -> "SharedView": ...
    def save_shared_view(self, session_id: str, view: "SharedView") -> None: ...


class DefaultMemoryBackend:
    """Production backend — wraps existing DB-backed modules.

    Stateless: all state lives in DB.  Safe to create per-request.
    """

    # ── Workflow ────────────────────────────────────────────────

    def load_workflow_item(self, session_id: str, agent_type: str) -> Any:
        if agent_type == "order":
            from agents.order.workflow_store import load as load_owf
            return load_owf(session_id)
        elif agent_type == "cart":
            from agents.cart.agent import _load_state
            return _load_state(session_id)
        elif agent_type == "purchase":
            from agents.purchase.workflow_store import load as load_pwf
            return load_pwf(session_id)
        return None

    # ── Session ─────────────────────────────────────────────────

    def recall_session(self, session_id: str) -> Any:
        from agents.graph.session_memory import get as get_session
        return get_session(session_id)

    def save_session(self, session_id: str, **kwargs) -> None:
        from agents.models import SessionState
        SessionState.objects.update_or_create(
            session_id=session_id,
            defaults={k: v for k, v in kwargs.items() if v is not None},
        )

    # ── User ────────────────────────────────────────────────────

    def recall_user(self, user_id: int) -> Any:
        from agents.graph.memory_manager import memory_manager
        return memory_manager.build(user_id)

    # ── Shared View ─────────────────────────────────────────────

    def recall_shared_view(self, session_id: str) -> "SharedView":
        from agents.models import SessionState
        from .types import SharedView
        row = SessionState.objects.filter(session_id=session_id).first()
        if row and row.shared_view:
            return SharedView(**row.shared_view)
        return SharedView()

    def save_shared_view(self, session_id: str, view: "SharedView") -> None:
        from agents.models import SessionState
        SessionState.objects.update_or_create(
            session_id=session_id,
            defaults={"shared_view": {
                "current_product": view.current_product,
                "cart_snapshot": view.cart_snapshot,
            }},
        )
