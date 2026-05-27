"""Cart workflow state machine: step enum, session state, transitions, and focus TTL."""

import time
from dataclasses import dataclass, field
from enum import Enum, auto


class CartStep(Enum):
    """Workflow steps for the cart agent."""
    IDLE = auto()
    VIEWING_CART = auto()
    FOCUSED_ITEM = auto()


# Seconds before a focused item is considered stale.
FOCUS_TTL = 300

# Valid transitions: current_step → allowed next steps.
_VALID_TRANSITIONS: dict[CartStep, set[CartStep]] = {
    CartStep.IDLE:           {CartStep.VIEWING_CART},
    CartStep.VIEWING_CART:   {CartStep.FOCUSED_ITEM, CartStep.IDLE},
    CartStep.FOCUSED_ITEM:   {CartStep.VIEWING_CART, CartStep.IDLE},
}


def validate_transition(current: CartStep, target: CartStep) -> None:
    """Raise ValueError if *target* is not reachable from *current*."""
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Invalid cart state transition: {current.name} → {target.name}"
        )


def is_focus_expired(state: "CartSessionState") -> bool:
    """Return True when the focused item's TTL has elapsed."""
    return (state.focused_at + FOCUS_TTL) < time.time()


@dataclass
class CartSessionState:
    """Mutable dataclass that tracks a single cart workflow session."""
    workflow_id: str
    current_step: CartStep = CartStep.IDLE
    focused_item: dict | None = None
    focused_at: float = 0.0
    selected_for_action: str = ""
