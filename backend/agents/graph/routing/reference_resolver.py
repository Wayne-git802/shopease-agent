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
class ReferenceTarget:
    """What the user is referring to — supports single and multi-product references.

    action: ReferenceAction value string (e.g. "add_to_cart", "purchase").
            Set by execution layer when mapping from ResolvedReference.
            Agent layer reads this — does NOT import ReferenceAction enum.
    quantity: number of units the user wants (e.g. "买3个" → 3). Default 1.
    """
    product_ids: list[int] = field(default_factory=list)
    action: str | None = None
    quantity: int = 1


@dataclass
class ReferenceContext:
    """Minimal context needed for reference resolution — no GraphState dependency."""
    products: list[ProductReference] = field(default_factory=list)
    last_query: str = ""


@dataclass
class ResolvedReference:
    """Result of reference resolution. All None → no reference detected."""
    target: ReferenceTarget = field(default_factory=ReferenceTarget)
    product_name: str = ""
    confidence: float = 0.0
    action: ReferenceAction | None = None
    capability: str | None = None
    clarification_reason: ClarificationReason | None = None
    source_index: int | None = None  # internal use, debugging only

    @property
    def requires_clarification(self) -> bool:
        """True when the system should ask the user for more information."""
        return self.clarification_reason is not None

    @property
    def has_product(self) -> bool:
        return len(self.target.product_ids) > 0

    @property
    def has_action(self) -> bool:
        return self.action is not None


# ═══════════════════════════════════════════════════════════════
# Patterns
# ═══════════════════════════════════════════════════════════════

_ORDINAL_PATTERN = re.compile(
    r'第\s*([\d一二两三四五六七八九十]+)\s*[个款]'
)

# Unit words for quantity extraction — common e-commerce measure words
_UNIT_WORDS: set[str] = {"个", "件", "台", "副", "盒", "箱", "包"}

# Quantity extraction: "3个", "5件", "两副", "十台" — independent of ordinal/action.
# Negative lookbehind (?<!第) prevents matching the ordinal's unit word
# (e.g. in "第二个" the "个" belongs to the ordinal, not a quantity).
_UNIT_CHARS = "".join(_UNIT_WORDS)
_QUANTITY_PATTERN = re.compile(
    rf'(?<!第)(\d+|[一两二三四五六七八九十]+)\s*[{_UNIT_CHARS}]'
)

# Shared keyword lists — also used by classifier._infer_action_from_clarification_reply
ACTION_KEYWORDS: dict[ReferenceAction, list[str]] = {
    ReferenceAction.PURCHASE:    ["购买", "下单", "买", "立即购买", "我要"],
    ReferenceAction.ADD_TO_CART: ["加入购物车", "加购", "加购物车"],
    ReferenceAction.VIEW_DETAIL: ["查看", "看看", "详情", "介绍", "什么样"],
}

_ACTION_PATTERNS: list[tuple[re.Pattern, ReferenceAction]] = [
    (re.compile(r'(买|购买|下单|我要)\s*(?:第\s*)?(\d+)\s*$'), ReferenceAction.PURCHASE),
    (re.compile(r'(加购物车|加入购物车|加购)\s*(?:第\s*)?(\d+)\s*$'), ReferenceAction.ADD_TO_CART),
    (re.compile(r'(看看|查看|详情|介绍|什么样)\s*(?:第\s*)?(\d+)\s*$'), ReferenceAction.VIEW_DETAIL),
    # Fallback patterns: action + intervening content (quantity, etc.) + ordinal.
    # Non-greedy .*? tolerates "买3个第二个" / "加购物车两个第一个" etc.
    (re.compile(r'(买|购买|下单|我要).*?第'), ReferenceAction.PURCHASE),
    (re.compile(r'(加购物车|加入购物车|加购).*?第'), ReferenceAction.ADD_TO_CART),
    (re.compile(r'(看看|查看|详情|介绍|什么样).*?第'), ReferenceAction.VIEW_DETAIL),
]

from ..utils import CN_DIGIT as _NUM_MAP

# AgentCapability 在 pipeline 模块，用字符串做 lazy mapping
_ACTION_CAPABILITY_MAP: dict[ReferenceAction, str] = {
    ReferenceAction.PURCHASE: "purchase",     # AgentCapability.PURCHASE
    ReferenceAction.ADD_TO_CART: "cart",      # AgentCapability.CART
    ReferenceAction.VIEW_DETAIL: "search",    # handled by entry_router → graph, not execution
}


def capability_for(action: ReferenceAction) -> str | None:
    return _ACTION_CAPABILITY_MAP.get(action)


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

    # Fallback: ordinal present but no structured pattern matched (e.g.
    # reversed-order "第二个买3个" where ordinal precedes action keyword).
    # Check for bare action keywords anywhere in the query, position-independent.
    if action is None:
        for act, keywords in ACTION_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                action = act
                break

    # ── 3. Extract quantity (independent step, not coupled to action/ordinal) ──
    # Handles "买3个第二个", "第二个买3个", "买第二个3个" equally.
    quantity: int = 1
    qty_match = _QUANTITY_PATTERN.search(query)
    if qty_match:
        qty_str = qty_match.group(1)
        if qty_str.isdigit():
            quantity = int(qty_str)
        else:
            quantity = _NUM_MAP.get(qty_str, 1)

    # ── 4. Lookup product from context ──
    product = None
    if ctx.products and 0 <= ref_idx < len(ctx.products):
        product = ctx.products[ref_idx]

    # ── 5. Determine clarification reason ──
    clarification_reason: ClarificationReason | None = None
    if product is None:
        clarification_reason = ClarificationReason.PRODUCT_NOT_FOUND
    # Bare ordinal ("第二个") → default to VIEW_DETAIL, not clarify
    if action is None and product is not None:
        action = ReferenceAction.VIEW_DETAIL

    return ResolvedReference(
        target=ReferenceTarget(
            product_ids=[product.product_id] if product else [],
            quantity=quantity,
        ),
        product_name=product.product_name if product else "",
        confidence=1.0 if product else 0.0,
        action=action,
        capability=capability_for(action) if (action is not None and product is not None) else None,
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
    assert r.target.product_ids == [102], f"Expected [102], got {r.target.product_ids}"
    assert r.capability == "purchase", f"Expected 'order', got {r.capability}"
    assert r.source_index == 2
    assert not r.requires_clarification
    print("PASS: 买第二个")

    # Test 2: ordinal only defaults to VIEW_DETAIL
    r = resolve_reference("第二个", ctx)
    assert r.action == ReferenceAction.VIEW_DETAIL, f"Expected VIEW_DETAIL, got {r.action}"
    assert r.target.product_ids == [102]
    assert r.capability == "search"
    assert r.clarification_reason is None
    assert not r.requires_clarification
    print("PASS: 第二个")

    # Test 3: index out of range
    r = resolve_reference("第十五个", ctx)
    assert r.clarification_reason == ClarificationReason.PRODUCT_NOT_FOUND
    assert r.target.product_ids == []
    assert r.capability is None
    assert r.requires_clarification
    print("PASS: 第十五个")

    # Test 4: first ordinal
    r = resolve_reference("加购物车第一个", ctx)
    assert r.action == ReferenceAction.ADD_TO_CART
    assert r.target.product_ids == [101]
    assert r.capability == "cart", f"Expected 'cart', got {r.capability}"
    assert r.source_index == 1
    assert not r.requires_clarification
    print("PASS: 加购物车第一个")

    # Test 5: no reference
    r = resolve_reference("推荐手机", ctx)
    assert r.target.product_ids == []
    assert r.action is None
    assert r.capability is None
    assert not r.requires_clarification
    print("PASS: 推荐手机 (no reference)")

    # Test 6: view detail
    r = resolve_reference("看看第二个", ctx)
    assert r.action == ReferenceAction.VIEW_DETAIL
    assert r.target.product_ids == [102]
    assert r.capability == "search", f"Expected 'search', got {r.capability}"
    print("PASS: 看看第二个")

    # Test 7: empty context
    r = resolve_reference("第一个", ReferenceContext())
    assert r.action is None
    assert r.target.product_ids == []
    assert r.capability is None
    assert r.clarification_reason == ClarificationReason.PRODUCT_NOT_FOUND
    print("PASS: 第一个 (empty context)")

    # Test 8: compound reference — quantity + ordinal ("买3个第二个")
    r = resolve_reference("买3个第二个", ctx)
    assert r.action == ReferenceAction.PURCHASE, f"Expected PURCHASE, got {r.action}"
    assert r.target.product_ids == [102], f"Expected [102], got {r.target.product_ids}"
    assert r.target.quantity == 3, f"Expected quantity=3, got {r.target.quantity}"
    assert r.capability == "purchase"
    print("PASS: 买3个第二个")

    # Test 9: reversed order — ordinal before quantity ("第二个买3个")
    r = resolve_reference("第二个买3个", ctx)
    assert r.action == ReferenceAction.PURCHASE, f"Expected PURCHASE, got {r.action}"
    assert r.target.product_ids == [102]
    assert r.target.quantity == 3, f"Expected quantity=3, got {r.target.quantity}"
    print("PASS: 第二个买3个")

    # Test 10: Chinese numeral quantity ("买两个第二个")
    r = resolve_reference("买两个第二个", ctx)
    assert r.action == ReferenceAction.PURCHASE, f"Expected PURCHASE, got {r.action}"
    assert r.target.quantity == 2, f"Expected quantity=2, got {r.target.quantity}"
    print("PASS: 买两个第二个")

    # Test 11: unit word variety — 耳机用"副" ("买3副第二个")
    r = resolve_reference("买3副第二个", ctx)
    assert r.target.quantity == 3, f"Expected quantity=3, got {r.target.quantity}"
    print("PASS: 买3副第二个")

    # Test 12: no quantity → default 1 ("买第二个")
    r = resolve_reference("买第二个", ctx)
    assert r.target.quantity == 1, f"Expected quantity=1, got {r.target.quantity}"
    print("PASS: 买第二个 (quantity default=1)")

    print("\nAll tests passed!")


if __name__ == "__main__":
    _self_test()
