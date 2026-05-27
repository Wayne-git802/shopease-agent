"""
Context Resolver — scope-aware reference resolution for CartAgent.

Handles:
  - "第二个" / "第2个" → resolve to concrete product_id from display or cart
  - "那个" / "这个" → resolve via focused_item (cart-scoped)
  - Scope disambiguation: display first, then cart, then fallback error

Follows the same pattern as agents/order/context_resolver.py but adapted
for cart scope with display-disambiguation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agents.graph.display_context import get_display
from .repository import get_cart_items


@dataclass
class ResolvedReference:
    """Result of resolving a user's positional/focus reference.

    Attributes:
        resolved: True if a concrete product_id was identified.
        source: Which scope resolved the reference — "display" | "cart" | "none".
        scope_id: display_id for display scope, "cart_{user_id}" for cart scope.
        product_id: Resolved product ID, or None if unresolved.
        name: Product display name, empty string if unresolved.
        index: 1-based index into the source list, 0 if unresolved or focus-based.
        error: Human-readable error message when resolved=False.
    """
    resolved: bool
    source: str             # "display" | "cart" | "none"
    scope_id: str           # display_id or "cart_{user_id}"
    product_id: int | None = None
    name: str = ""
    index: int = 0
    error: str = ""


def resolve(
    query: str,
    display_id: str | None,
    focused_item: dict | None,
    user_id: int | None = None,
    cart_items: list[dict] | None = None,
) -> ResolvedReference:
    """Resolve a positional/focus reference against display or cart scope.

    Priority order:
      1. INDEX reference (e.g. "第二个") → display first, then cart.
      2. FOCUS reference (e.g. "那个", "这个") → focused_item dict.
      3. Otherwise → unresolved.

    Args:
        query: Raw user utterance containing the reference.
        display_id: Current display ID (if the user is viewing results).
        focused_item: Dict with at least {product_id, name} when a cart item
                      is highlighted/focused in the UI.
        user_id: Authenticated user ID, used for cart lookups and scope_id.
        cart_items: Pre-fetched cart items (to avoid redundant DB calls).
                    If None and user_id is provided, falls back to
                    calling get_cart_items(user_id) for index resolution.

    Returns:
        ResolvedReference — check .resolved to know if resolution succeeded.
    """
    # ── 1. INDEX reference: "第二个", "第2个", "2个" ──
    index = _extract_index(query)
    if index is not None:
        return _resolve_index(index, display_id, user_id, cart_items)

    # ── 2. FOCUS reference: "那个", "这个" ──
    if _is_focus_reference(query):
        return _resolve_focus(focused_item, user_id)

    # ── 3. Unrecognized ──
    return ResolvedReference(
        resolved=False,
        source="none",
        scope_id="",
        error="无法识别的引用",
    )


# ═══════════════════════════════════════════════════════════════
# Internal resolvers
# ═══════════════════════════════════════════════════════════════

def _resolve_index(
    index: int,
    display_id: str | None,
    user_id: int | None,
    cart_items: list[dict] | None,
) -> ResolvedReference:
    """Try to resolve a 1-based positional index, display-first."""
    zero_index = index - 1  # convert to 0-based for list access

    # ── Try display scope ──
    if display_id:
        group = get_display(display_id)
        if group is not None:
            items = group.items  # tuple[DisplayedItem, ...]
            if 0 <= zero_index < len(items):
                item = items[zero_index]
                return ResolvedReference(
                    resolved=True,
                    source="display",
                    scope_id=display_id,
                    product_id=item.product_id,
                    name=item.name,
                    index=index,
                )

    # ── Try cart scope ──
    if cart_items is None and user_id is not None:
        try:
            cart_items = get_cart_items(user_id)
        except Exception:
            cart_items = []

    if cart_items and 0 <= zero_index < len(cart_items):
        item = cart_items[zero_index]
        scope_id = f"cart_{user_id}" if user_id else "cart"
        return ResolvedReference(
            resolved=True,
            source="cart",
            scope_id=scope_id,
            product_id=item["product_id"],
            name=item.get("name", ""),
            index=index,
        )

    # ── Neither scope worked ──
    return ResolvedReference(
        resolved=False,
        source="none",
        scope_id="",
        error=f"找不到第{index}个商品",
    )


def _resolve_focus(
    focused_item: dict | None,
    user_id: int | None,
) -> ResolvedReference:
    """Resolve a focus/demonstrative reference from the focused item."""
    if focused_item:
        scope_id = f"cart_{user_id}" if user_id else "cart"
        return ResolvedReference(
            resolved=True,
            source="cart",
            scope_id=scope_id,
            product_id=focused_item.get("product_id"),
            name=focused_item.get("name", ""),
        )

    return ResolvedReference(
        resolved=False,
        source="none",
        scope_id="",
        error="没有选中的商品",
    )


# ═══════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════

def _extract_index(query: str) -> int | None:
    """Extract a 1-based positional index from a Chinese reference.

    Matches patterns:
      - "第N个"      e.g. "第二个", "第10个"
      - "第 N 个"    e.g. "第 3 个" (with optional whitespace)
      - "N个"        e.g. "2个", "5个"
      - standalone "N" at start/end  e.g. "2" (bare digit)

    Returns the 1-based index as int, or None if no pattern matches.
    """
    # Chinese digit mapping
    _CN = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}

    # Pattern 1: "第N个" or "第 N 个"  (Arabic + Chinese digits)
    m = re.search(r"第[^0-9]{0,3}([0-9]+|[一二三四五六七八九十])[^0-9]{0,3}个", query)
    if m:
        raw = m.group(1)
        if raw.isdigit():
            return int(raw)
        return _CN.get(raw)

    # Pattern 2: "N个" (without 第)
    m = re.search(r"(?:^|\s)([0-9]+|[一二三四五六七八九十])\s*个", query)
    if m:
        raw = m.group(1)
        if raw.isdigit():
            return int(raw)
        return _CN.get(raw)

    # Pattern 3: bare digit at boundaries
    m = re.search(r"(?:^|\s)([0-9]+)(?:\s|$)", query)
    if m:
        return int(m.group(1))

    return None


def _is_focus_reference(query: str) -> bool:
    """Return True if query is a demonstrative/focus reference like '那个' or '这个'."""
    # Normalize whitespace and strip punctuation for matching
    cleaned = query.strip().rstrip("。！？.!?")
    return cleaned in ("那个", "这个", "这一个", "那一个", "它", "他")
