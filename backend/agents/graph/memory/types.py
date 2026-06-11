"""
Memory types — WorkflowState, SharedView, MemoryEvent.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.order.workflow_store import OrderWorkflow
    from agents.cart.agent import CartSessionState
    from agents.purchase.workflow_store import PurchaseWorkflow as PurchaseWF

_MISSING = object()


@dataclass
class WorkflowState:
    """Lazy-loaded workflow states. No DB query until property access."""

    _session_id: str
    _backend: "MemoryBackend"

    _order: Any = _MISSING
    _cart: Any = _MISSING
    _purchase: Any = _MISSING

    @property
    def order(self) -> "OrderWorkflow | None":
        if self._order is _MISSING:
            self._order = self._backend.load_workflow_item(self._session_id, "order")
        return self._order

    @property
    def cart(self) -> "CartSessionState | None":
        if self._cart is _MISSING:
            self._cart = self._backend.load_workflow_item(self._session_id, "cart")
        return self._cart

    @property
    def purchase(self) -> "PurchaseWF | None":
        if self._purchase is _MISSING:
            self._purchase = self._backend.load_workflow_item(self._session_id, "purchase")
        return self._purchase


@dataclass
class SharedView:
    """Cross-agent shared context. System-owned, not agent-owned.

    WorkflowState = what one agent is doing (execution state).
    SharedView   = what other agents need to see (shared context).
    """

    current_product: dict | None = None
    cart_snapshot: list[dict] = field(default_factory=list)


@dataclass
class MemoryEvent:
    """Audit/debug/replay. Phase 6: definition only, not wired."""

    type: str
    session_id: str
    user_id: int | None
    payload: dict
    timestamp: float
