"""
CartAgent response builder. Builds cart_card blocks for frontend.

Produces CartResponse with text, blocks, and metadata.
Also exposes build_handoff() as an orchestrator signal (plain dict, not CartResponse).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CartResponse:
    text: str                              # human-readable message
    blocks: list[dict] = field(default_factory=list)   # UI blocks for frontend
    metadata: dict = field(default_factory=dict)       # extra data (cart_count, etc)

    def to_dict(self) -> dict:
        return {
            "reply": self.text,
            "intent": "cart",
            "agent_type": "cart",
            "blocks": self.blocks,
            "actions": [],
            "metadata": self.metadata,
            "ui_state": "done",
        }


# ── block builders ──────────────────────────────────────────────────────────

def build_cart_view(items: list[dict]) -> CartResponse:
    """Build response showing the full cart contents."""
    if not items:
        return CartResponse(text="您的购物车是空的。")

    count = len(items)
    lines = [f"您的购物车有{count}件商品："]
    for item in items:
        qty = item.get("quantity", 1)
        lines.append(f"  · {item.get('name', '')} ×{qty}  ¥{item.get('price', 0)}")

    return CartResponse(
        text="\n".join(lines),
        blocks=[{"type": "cart_card", "data": {"items": items}}],
        metadata={"cart_count": count},
    )


def build_added(item: dict, cart_count: int) -> CartResponse:
    """Build response after an item is added to the cart."""
    name = item.get("name", "")
    return CartResponse(
        text=f"已将{name}加入购物车 ✅ (共{cart_count}件)",
        blocks=[{"type": "cart_card", "data": {"items": [item], "cart_count": cart_count}}],
        metadata={"cart_count": cart_count},
    )


def build_removed(name: str, cart_count: int) -> CartResponse:
    """Build response after an item is removed from the cart."""
    return CartResponse(
        text=f"已移除{name} ✅ (剩余{cart_count}件)",
        metadata={"cart_count": cart_count},
    )


def build_updated(item: dict) -> CartResponse:
    """Build response after an item's quantity is updated."""
    name = item.get("name", "")
    qty = item.get("quantity", 0)
    return CartResponse(
        text=f"{name}数量已更新为{qty}",
        blocks=[{"type": "cart_card", "data": {"items": [item]}}],
    )


def build_error(message: str) -> CartResponse:
    """Build an error response."""
    return CartResponse(text=message)


# ── orchestrator signals ────────────────────────────────────────────────────

def build_handoff() -> dict:
    """Orchestrator handoff signal — NOT a CartResponse.

    Returns a plain dict that the orchestrator uses to transfer control
    to the purchase agent.
    """
    return {
        "status": "handoff",
        "target_agent": "purchase",
        "message": "正在跳转到结算...",
    }
