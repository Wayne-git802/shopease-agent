"""
Reference Resolver — extract ordinal reference + action from user query,
lookup the referenced product from previous assistant message blocks.

Does NOT depend on GraphState or full session — only takes ReferenceContext.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════


class ReferenceAction(StrEnum):
    """User action expressed alongside the reference."""
    PURCHASE = "purchase"
    ADD_TO_CART = "add_to_cart"
    VIEW_DETAIL = "view_detail"


class ClarificationReason(StrEnum):
    """Why the system needs to ask the user for more information."""
    ACTION_MISSING = "action_missing"       # product identified but no action (e.g. "第二个")
    PRODUCT_NOT_FOUND = "product_not_found"  # action present but product not found (e.g. "第十五个")


@dataclass
class ProductReference:
    """A product from a previous assistant message block."""
    product_id: int
    product_name: str


@dataclass
class ReferenceContext:
    """Minimal context needed for reference resolution — no GraphState dependency."""
    products: list[ProductReference] = field(default_factory=list)
    last_query: str = ""


@dataclass
class ResolvedReference:
    """Result of reference resolution. All None → no reference detected."""
    product_id: int | None = None
    product_name: str = ""
    confidence: float = 0.0
    action: ReferenceAction | None = None
    source_index: int | None = None
    clarification_reason: ClarificationReason | None = None

    @property
    def requires_clarification(self) -> bool:
        """True when the system should ask the user for more information."""
        return self.clarification_reason is not None

    @property
    def has_product(self) -> bool:
        return self.product_id is not None

    @property
    def has_action(self) -> bool:
        return self.action is not None


# ═══════════════════════════════════════════════════════════════
# Patterns
# ═══════════════════════════════════════════════════════════════

_ORDINAL_PATTERN = re.compile(
    r'第\s*([\d一二两三四五六七八九十]+)\s*[个款]'
)

# Reserved for future — pointer references like "这个", "那个", "就它"
_POINTER_PATTERNS: list[re.Pattern] = [
    # re.compile(r'(这个|那个|它|就它|就这个)')
]

_ACTION_PATTERNS: list[tuple[re.Pattern, ReferenceAction]] = [
    (re.compile(r'(买|购买|下单|我要)\s*第'), ReferenceAction.PURCHASE),
    (re.compile(r'(加购物车|加入购物车|加购)\s*第'), ReferenceAction.ADD_TO_CART),
    (re.compile(r'(看看|查看|详情|介绍|什么样)\s*第'), ReferenceAction.VIEW_DETAIL),
]

_NUM_MAP: dict[str, int] = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


# ═══════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════


def resolve_reference(query: str, ctx: ReferenceContext) -> ResolvedReference:
    """Extract ordinal + action from query, lookup product from ReferenceContext.

    Returns ResolvedReference with all fields populated when a reference is detected.
    Returns ResolvedReference() (all None) when no reference pattern matches.
    """
    # ── 1. Extract ordinal index ──
    ordinal_match = _ORDINAL_PATTERN.search(query)
    if not ordinal_match:
        return ResolvedReference()

    num_str = ordinal_match.group(1)
    ref_idx = _NUM_MAP.get(num_str, int(num_str) if num_str.isdigit() else 0) - 1

    # ── 2. Extract action ──
    action: ReferenceAction | None = None
    for pattern, act in _ACTION_PATTERNS:
        if pattern.search(query):
            action = act
            break

    # ── 3. Lookup product from context ──
    product = None
    if ctx.products and 0 <= ref_idx < len(ctx.products):
        product = ctx.products[ref_idx]

    # ── 4. Determine clarification reason ──
    clarification_reason: ClarificationReason | None = None
    if product is None:
        clarification_reason = ClarificationReason.PRODUCT_NOT_FOUND
    elif action is None:
        clarification_reason = ClarificationReason.ACTION_MISSING

    return ResolvedReference(
        product_id=product.product_id if product else None,
        product_name=product.product_name if product else "",
        confidence=1.0 if product else 0.0,
        action=action,
        source_index=ref_idx + 1,  # 1-indexed for human-readable
        clarification_reason=clarification_reason,
    )


# ═══════════════════════════════════════════════════════════════
# Quick test helpers (delete before merge, useful for PR review)
# ═══════════════════════════════════════════════════════════════


def _self_test() -> None:
    """Basic smoke tests for resolve_reference."""
    ctx = ReferenceContext(
        products=[
            ProductReference(product_id=101, product_name="华为FreeBuds 6i"),
            ProductReference(product_id=102, product_name="小米Buds 5 Pro"),
        ],
        last_query="手机",
    )

    # Test 1: action + product
    r = resolve_reference("买第二个", ctx)
    assert r.action == ReferenceAction.PURCHASE, f"Expected PURCHASE, got {r.action}"
    assert r.product_id == 102, f"Expected 102, got {r.product_id}"
    assert r.source_index == 2
    assert not r.requires_clarification
    print("PASS: 买第二个")

    # Test 2: ordinal only, no action
    r = resolve_reference("第二个", ctx)
    assert r.action is None
    assert r.product_id == 102
    assert r.clarification_reason == ClarificationReason.ACTION_MISSING
    assert r.requires_clarification
    print("PASS: 第二个")

    # Test 3: index out of range
    r = resolve_reference("第十五个", ctx)
    assert r.clarification_reason == ClarificationReason.PRODUCT_NOT_FOUND
    assert r.product_id is None
    assert r.requires_clarification
    print("PASS: 第十五个")

    # Test 4: first ordinal
    r = resolve_reference("加购物车第一个", ctx)
    assert r.action == ReferenceAction.ADD_TO_CART
    assert r.product_id == 101
    assert r.source_index == 1
    assert not r.requires_clarification
    print("PASS: 加购物车第一个")

    # Test 5: no reference
    r = resolve_reference("推荐手机", ctx)
    assert r.product_id is None
    assert r.action is None
    assert not r.requires_clarification
    print("PASS: 推荐手机 (no reference)")

    # Test 6: view detail
    r = resolve_reference("看看第二个", ctx)
    assert r.action == ReferenceAction.VIEW_DETAIL
    assert r.product_id == 102
    print("PASS: 看看第二个")

    # Test 7: empty context
    r = resolve_reference("第一个", ReferenceContext())
    assert r.action is None
    assert r.product_id is None
    assert r.clarification_reason == ClarificationReason.PRODUCT_NOT_FOUND
    print("PASS: 第一个 (empty context)")

    print("\nAll tests passed!")


if __name__ == "__main__":
    _self_test()
