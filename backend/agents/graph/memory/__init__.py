"""
AgentMemory — request-scoped memory facade for agents.

Usage:
    memory = AgentMemory()
    wf = memory.recall_workflow(session_id)
    view = memory.get_shared_view(session_id)

Layers:
    AgentMemory    Request-scoped facade + SharedView cache
    MemoryService  Thin middle layer (Phase 6: pass-through, 6b: cache/events)
    MemoryBackend  Pluggable storage (DefaultMemoryBackend wraps existing DB modules)
"""

from .backend import MemoryBackend, DefaultMemoryBackend
from .types import WorkflowState, SharedView


class MemoryService:
    """Thin middle layer. Phase 6: pass-through. Phase 6b: cache/events."""

    def __init__(self, backend: MemoryBackend):
        self._b = backend

    def recall_workflow(self, session_id: str) -> WorkflowState:
        return WorkflowState(_session_id=session_id, _backend=self._b)

    def recall_session(self, session_id: str):
        return self._b.recall_session(session_id)

    def save_session(self, session_id: str, **kwargs) -> None:
        self._b.save_session(session_id, **kwargs)

    def recall_user(self, user_id: int):
        return self._b.recall_user(user_id)

    def recall_shared_view(self, session_id: str) -> SharedView:
        return self._b.recall_shared_view(session_id)

    def save_shared_view(self, session_id: str, view: SharedView) -> None:
        self._b.save_shared_view(session_id, view)


class AgentMemory:
    """Request-scoped memory facade. One instance per pipeline invocation.

    Holds request-level cache for SharedView — inside a handoff loop,
    CartAgent writes to cache first (DB backup), PurchaseAgent reads
    from cache (zero DB round-trip in the same handoff loop).
    """

    def __init__(self, backend: MemoryBackend | None = None):
        self._b = backend or DefaultMemoryBackend()
        self._service = MemoryService(self._b)
        self._shared_cache: dict[str, SharedView] = {}

    # ── Workflow ────────────────────────────────────────────────

    def recall_workflow(self, session_id: str) -> WorkflowState:
        return self._service.recall_workflow(session_id)

    # ── Session ─────────────────────────────────────────────────

    def recall_session(self, session_id: str):
        return self._service.recall_session(session_id)

    def save_session(self, session_id: str, **kwargs) -> None:
        self._service.save_session(session_id, **kwargs)

    # ── User ────────────────────────────────────────────────────

    def recall_user(self, user_id: int):
        return self._service.recall_user(user_id)

    # ── Shared View (request-level cache) ───────────────────────

    def get_shared_view(self, session_id: str) -> SharedView:
        if session_id in self._shared_cache:
            return self._shared_cache[session_id]
        view = self._service.recall_shared_view(session_id)
        self._shared_cache[session_id] = view
        return view

    def set_shared_view(self, session_id: str, **kwargs) -> None:
        if session_id not in self._shared_cache:
            self._shared_cache[session_id] = SharedView()
        for k, v in kwargs.items():
            setattr(self._shared_cache[session_id], k, v)
        self._service.save_shared_view(session_id, self._shared_cache[session_id])
