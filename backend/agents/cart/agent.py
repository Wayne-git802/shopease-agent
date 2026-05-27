"""
CartAgent — main entry point. Pipeline: parse→resolve→execute→respond.

Fixed pipeline like OrderAgent:
  1. Auth gate (user_id required)
  2. Load/init CartSessionState (in-process dict, no DB)
  3. Parse intent via keyword-weight rules
  4. Resolve context (display → cart scope)
  5. Execute operation based on intent
  6. Return structured response dict

Session state lives in an in-process dict keyed by session_id.
TTL is handled by CartSessionState.focused_item expiry (is_focus_expired).
No DB persistence — cart state is memory-only, like session_memory.py.
"""

from __future__ import annotations

import uuid
import logging
import re

from .state_machine import CartStep, CartSessionState, validate_transition, is_focus_expired
from .intent_parser import parse as parse_intent, CartIntent
from .context_resolver import resolve as resolve_context
from .repository import (
    add_to_cart,
    remove_item,
    update_quantity,
    get_cart_items,
    get_cart_count,
)

logger = logging.getLogger(__name__)

# ── In-process CartSessionState store ───────────────────────────
# Pattern follows agents/graph/session_memory.py:
#   in-process dict keyed by session_id, TTL handled by state machine.
#   No DB — CartSessionState lives in memory only.

_store: dict[str, CartSessionState] = {}


def _load_state(session_id: str) -> CartSessionState:
    """Load or initialize CartSessionState for the session.

    Auto-expires stale focused_item via is_focus_expired().
    """
    state = _store.get(session_id)
    if state is None:
        state = CartSessionState(workflow_id=f"wf_{uuid.uuid4().hex[:16]}")
        _store[session_id] = state
    # Check focus TTL on every load
    if state.focused_item and is_focus_expired(state):
        state.focused_item = None
        state.focused_at = 0.0
    return state


def _save_state(session_id: str, state: CartSessionState) -> None:
    """Persist CartSessionState to in-process store."""
    _store[session_id] = state


# ── Response builders ───────────────────────────────────────────

def build_error(message: str) -> dict:
    """Build an error response dict."""
    return {
        "reply": message,
        "intent": "cart",
        "agent_type": "cart",
        "blocks": [],
        "actions": [],
        "metadata": {},
        "ui_state": "done",
    }


def build_added(result: dict, cart_count: int) -> dict:
    """Build response for a successful cart addition."""
    name = result.get("name", "商品")
    qty = result.get("quantity", 1)
    return {
        "reply": f"已将 {name} 加入购物车（数量：{qty}）。购物车共 {cart_count} 件商品。",
        "intent": "cart",
        "agent_type": "cart",
        "blocks": [{
            "type": "cart_update",
            "data": {"action": "added", "product": result, "cart_count": cart_count},
        }],
        "actions": ["查看购物车", "结算"],
        "metadata": {"cart_count": cart_count},
        "ui_state": "done",
    }


def build_cart_view(items: list[dict]) -> dict:
    """Build response for cart contents listing."""
    if not items:
        return {
            "reply": "购物车是空的。",
            "intent": "cart",
            "agent_type": "cart",
            "blocks": [],
            "actions": [],
            "metadata": {"cart_count": 0},
            "ui_state": "done",
        }

    lines = ["你的购物车："]
    blocks = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item['name']} ×{item['quantity']} — ¥{item['price']}")
        blocks.append({"type": "cart_item", "data": item})

    total = sum(float(item["price"]) * int(item["quantity"]) for item in items)
    lines.append(f"\n共 {len(items)} 件，合计 ¥{total:.2f}")
    lines.append("回复「结算」去下单，回复「删除 + 编号」移除商品。")

    return {
        "reply": "\n".join(lines),
        "intent": "cart",
        "agent_type": "cart",
        "blocks": blocks,
        "actions": ["结算", "删除"],
        "metadata": {"cart_count": len(items), "total": round(total, 2)},
        "ui_state": "done",
    }


def build_removed(name: str, cart_count: int) -> dict:
    """Build response for a successful item removal."""
    return {
        "reply": f"已从购物车移除 {name}。购物车还剩 {cart_count} 件商品。",
        "intent": "cart",
        "agent_type": "cart",
        "blocks": [{
            "type": "cart_update",
            "data": {"action": "removed", "name": name, "cart_count": cart_count},
        }],
        "actions": ["查看购物车", "结算"],
        "metadata": {"cart_count": cart_count},
        "ui_state": "done",
    }


def build_updated(result: dict) -> dict:
    """Build response for a successful quantity update."""
    pid = result.get("product_id", "")
    qty = result.get("new_quantity", 0)
    return {
        "reply": f"商品数量已更新为 {qty}。",
        "intent": "cart",
        "agent_type": "cart",
        "blocks": [{
            "type": "cart_update",
            "data": {"action": "updated", "product_id": pid, "quantity": qty},
        }],
        "actions": ["查看购物车", "结算"],
        "metadata": {},
        "ui_state": "done",
    }


def build_handoff() -> dict:
    """Build a checkout handoff signal for the orchestrator.

    NOT a CartResponse — this signals the orchestrator to route
    to the PurchaseAgent for checkout flow.
    """
    return {
        "_handoff": "purchase",
        "intent": "cart",
        "agent_type": "cart",
        "reply": "",
        "blocks": [],
        "actions": [],
        "metadata": {"checkout": True},
        "ui_state": "done",
    }


# ── Quantity extraction helper ──────────────────────────────────

def _extract_quantity(query: str) -> int | None:
    """Extract a quantity integer from the query string via regex \\d+.

    Returns None if no digits found.
    """
    m = re.search(r"(\d+)", query)
    if m:
        return int(m.group(1))
    return None


# ── Main entry point ────────────────────────────────────────────

def run(
    query: str,
    user_id: int | None = None,
    session_id: str = "",
    display_id: str = "",
) -> dict:
    """Main entry point. Handles ONE turn of cart conversation.

    Pipeline: parse→resolve→execute→respond.
    """

    # ── Step 1: Auth gate ──────────────────────────────────
    if not user_id:
        return build_error("请先登录")

    # ── Step 2: Load/init session state ────────────────────
    state = _load_state(session_id)

    # ── Step 3: Parse intent ───────────────────────────────
    parsed = parse_intent(query)

    # Unknown intent → fallback to orchestrator
    if parsed.intent == "unknown":
        return {"_fallback": True, "reply": query}

    # ── Step 4: Resolve context ────────────────────────────
    # Pass current focused_item from session state so focus-based
    # references ("那个"/"这个") resolve against the focused item.
    focused = state.focused_item
    resolved = resolve_context(
        query=query,
        display_id=display_id or None,
        focused_item=focused,
        user_id=user_id,
    )

    # ── Step 5: Execute by intent ──────────────────────────

    intent = parsed.intent

    # ── ADD_TO_CART ──
    if intent == CartIntent.ADD_TO_CART:
        product_id = None

        # a. Resolved reference → use product_id directly
        if resolved.resolved:
            product_id = resolved.product_id

        # b. Else try display fallback: get first item from display
        elif display_id:
            from agents.graph.display_context import get_display
            group = get_display(display_id)
            if group is not None and group.items:
                product_id = group.items[0].product_id

        if not product_id:
            return build_error("请指定要加入购物车的商品")

        # c. Validate transition: IDLE → VIEWING_CART
        try:
            validate_transition(CartStep.IDLE, CartStep.VIEWING_CART)
        except ValueError:
            pass  # Non-blocking for add — force the state change

        # d. Execute
        result = add_to_cart(user_id, product_id)
        count = get_cart_count(user_id)

        # e. Update state
        state.current_step = CartStep.VIEWING_CART
        _save_state(session_id, state)

        final = build_added(result, count)

    # ── VIEW_CART ──
    elif intent == CartIntent.VIEW_CART:
        # a. Validate transition: any → VIEWING_CART
        #    Viewing is safe from any state; log failure but proceed.
        try:
            validate_transition(state.current_step, CartStep.VIEWING_CART)
        except ValueError:
            pass

        # b. Fetch items
        items = get_cart_items(user_id)

        # c. Update state
        state.current_step = CartStep.VIEWING_CART
        _save_state(session_id, state)

        final = build_cart_view(items)

    # ── REMOVE_FROM_CART ──
    elif intent == CartIntent.REMOVE_FROM_CART:
        # a. Must have resolved product_id
        if not resolved.resolved or not resolved.product_id:
            return build_error("请指定要删除的商品")

        product_id = resolved.product_id
        name = resolved.name or "商品"

        # b. Execute
        remove_item(user_id, product_id)
        count = get_cart_count(user_id)

        final = build_removed(name, count)

    # ── UPDATE_QTY ──
    elif intent == CartIntent.UPDATE_QTY:
        # a. Must have resolved product_id + extracted quantity
        if not resolved.resolved or not resolved.product_id:
            return build_error("请指定要修改数量的商品")

        qty = _extract_quantity(query)
        if qty is None:
            return build_error("请指定新的数量")

        # b. Execute
        result = update_quantity(user_id, resolved.product_id, qty)

        final = build_updated(result)

    # ── CHECKOUT ──
    elif intent == CartIntent.CHECKOUT:
        # a. Check cart not empty
        items = get_cart_items(user_id)
        if not items:
            return build_error("购物车是空的")

        # b. Handoff to orchestrator → PurchaseAgent
        final = build_handoff()

    # ── DECLINE ──
    elif intent == CartIntent.DECLINE:
        # a. Transition to IDLE
        state.current_step = CartStep.IDLE
        state.focused_item = None
        state.focused_at = 0.0
        _save_state(session_id, state)

        final = build_error("好的，已取消")

    else:
        # Should not reach here (parse returns CartIntent values or "unknown")
        return {"_fallback": True, "reply": query}

    # ── Step 6: Return ─────────────────────────────────────
    final["session_id"] = session_id
    final["agent_type"] = "cart"
    return final
