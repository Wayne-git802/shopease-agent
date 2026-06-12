"""
ReferenceResolver — legacy product reference resolution for domain agents.

⚠️  NOTE: This module is the OLD reference resolver used internally by
PurchaseAgent and CartAgent for product reference resolution during
agent execution.  It defines its own LegacyResolvedReference (incompatible
with routing/reference_resolver.ResolvedReference).

For routing-time reference resolution (action detection, capability routing,
clarification), see routing/reference_resolver.py instead.

One resolve() function handles:
  1. DisplayContext lookups (when user says "第一个", "第二个")
  2. Focused-item pronoun resolution (when user says "那个", "这个")
  3. Block-based implicit references (when user says "买这个", "加购")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agents.graph.display_context import get_display

logger = logging.getLogger(__name__)


@dataclass
class LegacyResolvedReference:
    """Result of resolving a product reference.

    Attributes:
        source: Which resolution strategy succeeded.
                "display" | "focus" | "block" | None
        product_id: Concrete product ID, or 0 if unresolved.
        confidence: 0.0 – 1.0 confidence score.
        name: Product display name, empty string if unresolved or unknown.
        price: Product price, 0.0 if unresolved or unknown.
    """
    source: str | None       # "display" | "focus" | "block" | None
    product_id: int
    confidence: float        # 0.0 – 1.0
    name: str = ""
    price: float = 0.0


def resolve(
    session_id: str,
    display_id: str = "",
    query: str = "",
    focused_item: dict | None = None,
    reference_type: str = "",        # "index" | "pronoun" | "implicit"
    reference_value: int | None = None,  # index number (0-based)
) -> LegacyResolvedReference:
    """Resolve a product reference using the first matching strategy.

    Resolution order (short-circuits on first match):

    1. DisplayContext — when display_id is provided and reference_type="index".
       Looks up the display snapshot and returns the item at reference_value.
       source="display", confidence=0.95

    2. Focused item — when focused_item is provided and reference_type="pronoun".
       Pronoun means "那个", "这个", "it" — user refers to the last item they
       focused on.  Returns focused_item['product_id'].
       source="focus", confidence=0.85

    3. Latest block — when reference_type="implicit" (or empty/no special type).
       "买这个", "加购" — implicit reference to the most recently displayed
       product.  Queries AgentConversation for the most recent product_card block.
       source="block", confidence=0.70

    4. No match — source=None, product_id=0, confidence=0.0

    Args:
        session_id: Current conversation session ID (used for block lookups).
        display_id: Display snapshot ID.  Empty string → skip display lookup.
        query: Raw user utterance.  Not parsed here; callers pre-extract
               reference_type and reference_value from the query.
        focused_item: Dict with optional keys {product_id, name, price}.
                      Represents the currently focused/highlighted cart item.
        reference_type: "index" | "pronoun" | "implicit" | "".
        reference_value: 0-based positional index (only meaningful when
                         reference_type="index").

    Returns:
        LegacyResolvedReference with source, product_id, confidence, name, price.
        Unresolved references have source=None, product_id=0, confidence=0.0.
    """
    # ── 1. DisplayContext lookup ──────────────────────────────────
    if display_id and reference_type == "index" and reference_value is not None:
        result = _resolve_display(display_id, reference_value)
        if result is not None:
            return result

    # ── 2. Focused item (pronoun resolution) ──────────────────────
    if focused_item and reference_type == "pronoun":
        result = _resolve_focus(focused_item)
        if result is not None:
            return result

    # ── 3. Latest block (implicit reference) ──────────────────────
    if reference_type in ("implicit", ""):
        result = _resolve_block(session_id)
        if result is not None:
            return result

    # ── 4. No match ───────────────────────────────────────────────
    return LegacyResolvedReference(
        source=None,
        product_id=0,
        confidence=0.0,
    )


# ═══════════════════════════════════════════════════════════════
# Internal resolvers
# ═══════════════════════════════════════════════════════════════

def _resolve_display(display_id: str, index: int) -> LegacyResolvedReference | None:
    """Try to resolve via DisplayContext snapshot.

    Args:
        display_id: Display snapshot ID.
        index: 0-based positional index into the display items list.

    Returns:
        LegacyResolvedReference on success, None if display not found or index out of range.
    """
    group = get_display(display_id)
    if group is None:
        logger.debug("_resolve_display: display_id=%s not found or expired", display_id)
        return None

    items = group.items  # tuple[DisplayedItem, ...]
    if index < 0 or index >= len(items):
        logger.debug(
            "_resolve_display: index=%d out of range [0, %d) for display_id=%s",
            index, len(items), display_id,
        )
        return None

    item = items[index]
    return LegacyResolvedReference(
        source="display",
        product_id=item.product_id,
        confidence=0.95,
        name=item.name,
        price=item.price,
    )


def _resolve_focus(focused_item: dict) -> LegacyResolvedReference | None:
    """Try to resolve via focused_item (pronoun/demonstrative).

    Args:
        focused_item: Dict with optional keys {product_id, name, price}.

    Returns:
        LegacyResolvedReference on success, None if product_id is missing/None.
    """
    product_id = focused_item.get("product_id")
    if product_id is None:
        logger.debug("_resolve_focus: focused_item has no product_id")
        return None

    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        logger.debug("_resolve_focus: product_id=%r is not a valid int", product_id)
        return None

    return LegacyResolvedReference(
        source="focus",
        product_id=product_id,
        confidence=0.85,
        name=focused_item.get("name", ""),
        price=float(focused_item.get("price", 0.0)),
    )


def _resolve_block(session_id: str) -> LegacyResolvedReference | None:
    """Try to resolve via the most recent product_card block in conversation history.

    Queries AgentConversation for the last 5 assistant messages, scans their
    metadata.blocks for "product_card" type, and returns the most recent product
    found.

    Args:
        session_id: Current conversation session ID.

    Returns:
        LegacyResolvedReference on success, None if no product_card blocks found.
    """
    try:
        from agents.models import AgentConversation

        msgs = (
            AgentConversation.objects
            .filter(session_id=session_id, role="assistant")
            .order_by("-created_at")[:5]
        )
    except Exception:
        logger.warning("_resolve_block: failed to query AgentConversation")
        return None

    if not msgs:
        logger.debug("_resolve_block: no assistant messages for session_id=%s", session_id)
        return None

    # Scan messages newest-first; return the first product found
    for msg in msgs:
        if not msg.metadata:
            continue

        blocks = msg.metadata.get("blocks", [])
        if not blocks:
            continue

        for block in blocks:
            if block.get("type") != "product_card":
                continue

            data = block.get("data", {})
            if not data:
                continue

            # product_card blocks may have a single product or a list of products.
            # Use the first product from "products" list, or the data dict itself.
            products = data.get("products")
            if isinstance(products, list) and products:
                p = products[0]
            else:
                p = data

            product_id = p.get("product_id") or p.get("id")
            if product_id is None:
                continue

            try:
                product_id = int(product_id)
            except (TypeError, ValueError):
                continue

            return LegacyResolvedReference(
                source="block",
                product_id=product_id,
                confidence=0.70,
                name=p.get("name", ""),
                price=float(p.get("price", 0.0)),
            )

    logger.debug("_resolve_block: no product_card blocks found in session_id=%s", session_id)
    return None
