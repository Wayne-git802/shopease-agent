"""
Tools — executable operations for OrderAgent.

Each tool delegates to repository. No business logic, no validation.
ToolRisk enum classifies operations for confirmation gating.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional


class ToolRisk(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE_WRITE = "irreversible_write"


TOOL_RISK: dict[str, ToolRisk] = {
    "query_orders":   ToolRisk.READ_ONLY,
    "order_detail":   ToolRisk.READ_ONLY,
    "logistics":      ToolRisk.READ_ONLY,
    "cancel_order":   ToolRisk.IRREVERSIBLE_WRITE,
    "request_refund": ToolRisk.IRREVERSIBLE_WRITE,
}


def requires_confirmation(tool_name: str) -> bool:
    return TOOL_RISK.get(tool_name) == ToolRisk.IRREVERSIBLE_WRITE


# ═══════════════════════════════════════════════════════════
# Tool implementations
# ═══════════════════════════════════════════════════════════

def query_orders(user_id: int) -> list[dict]:
    from .repository import get_user_orders
    return get_user_orders(user_id)


def order_detail(user_id: int, order_id: int) -> dict | None:
    from .repository import get_order_detail
    return get_order_detail(user_id, order_id)


def check_logistics(user_id: int, order_id: int) -> dict:
    from .repository import get_logistics
    return get_logistics(user_id, order_id)


def cancel_order(user_id: int, order_id: int, idempotency_key: str | None = None) -> dict:
    from .repository import cancel_order
    return cancel_order(user_id, order_id, idempotency_key)


def request_refund(
    user_id: int, order_id: int, reason: str = "",
    idempotency_key: str | None = None,
) -> dict:
    from .repository import create_refund
    return create_refund(user_id, order_id, reason, idempotency_key)


# ═══════════════════════════════════════════════════════════
# Tool executor
# ═══════════════════════════════════════════════════════════

def execute(tool_name: str, user_id: int, order_id: int | None = None,
            reason: str = "", idempotency_key: str | None = None) -> dict:
    """Execute a tool by name."""
    tools = {
        "query_orders":   lambda: query_orders(user_id),
        "order_detail":   lambda: order_detail(user_id, order_id or 0),
        "logistics":      lambda: check_logistics(user_id, order_id or 0),
        "cancel_order":   lambda: cancel_order(user_id, order_id or 0, idempotency_key),
        "request_refund": lambda: request_refund(user_id, order_id or 0, reason, idempotency_key),
    }
    fn = tools.get(tool_name)
    if not fn:
        return {"ok": False, "error": f"未知操作: {tool_name}"}
    return fn()
