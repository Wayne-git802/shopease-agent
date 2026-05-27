"""
Display Context — immutable per-display snapshot of products shown to user.

Used by CartAgent to resolve "加购第一个" → concrete product_id.
Every display gets a unique display_id; the UI passes this back so the
agent can look up exactly which products were shown.

Immutability Contract
---------------------
Once created via put_display(), a DisplayGroup is NEVER modified.
DisplayedItem is @dataclass(frozen=True); the items tuple is immutable.
If put_display() is called with an existing display_id, the call is
refused (logged warning) — displays are write-once.

Lifecycle
---------
- Created by recommend/search nodes when rendering products to the UI
- Consumed by CartAgent / order_node when user references "第一个"/"第二个"
- Auto-expired after TTL (300s) — get_display evicts stale entries on read
- cleanup_expired() for background/batch eviction

Storage: in-process dict (fast, zero-dependency).  Displays are
short-lived (< 5 min); no persistence needed.
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TTL_SECONDS = 300  # 5 minutes — displays are ephemeral


@dataclass(frozen=True)
class DisplayedItem:
    """A single product item as displayed in the UI.

    Attributes:
        ref_id: Stable reference (v1: str(product_id), v2: uuid).
                Used to resolve user references like "第一个".
        display_index: 1-based position in the UI list.
                       NEVER use as identity — position is ephemeral.
        product_id: Raw product ID from the catalog.
        name: Product display name.
        price: Product price.
    """
    ref_id: str
    display_index: int
    product_id: int
    name: str
    price: float


@dataclass(frozen=True)
class DisplayGroup:
    """Immutable snapshot of a single UI render.

    Attributes:
        display_id: Unique per-render identifier (e.g. "disp_" + uuid hex).
        source_type: Origin of the display: "recommend" | "search" | "cart".
        items: Tuple of DisplayedItem in UI order (immutable).
        created_at: Unix timestamp for TTL expiry.
    """
    display_id: str
    source_type: str
    items: tuple[DisplayedItem, ...]
    created_at: float = field(default_factory=time.time)


# ── In-process store ──────────────────────────────────────────────

_store: dict[str, DisplayGroup] = {}


def put_display(
    display_id: str,
    source_type: str,
    items: list[dict],
) -> DisplayGroup:
    """Store a display snapshot.  Write-once: refuses duplicate display_id.

    Args:
        display_id: Unique render identifier.
        source_type: "recommend" | "search" | "cart".
        items: List of dicts, each with {product_id, name, price}.

    Returns:
        The newly created DisplayGroup.

    Raises:
        ValueError: If display_id already exists in the store.
    """
    if display_id in _store:
        logger.warning(
            "put_display: display_id=%s already exists — refusing overwrite "
            "(immutable contract).  Caller should generate a fresh display_id.",
            display_id,
        )
        raise ValueError(
            f"DisplayGroup {display_id} already exists; displays are immutable. "
            f"Use a new display_id."
        )

    displayed_items = tuple(
        DisplayedItem(
            ref_id=str(item["product_id"]),  # v1: product_id as string
            display_index=i + 1,             # 1-based
            product_id=item["product_id"],
            name=item["name"],
            price=item["price"],
        )
        for i, item in enumerate(items)
    )

    group = DisplayGroup(
        display_id=display_id,
        source_type=source_type,
        items=displayed_items,
    )
    _store[display_id] = group
    return group


def get_display(display_id: str) -> DisplayGroup | None:
    """Retrieve a display snapshot by ID.  Auto-evicts expired entries.

    Returns None if the display is not found or has expired.
    """
    group = _store.get(display_id)
    if group is None:
        return None
    if time.time() - group.created_at > TTL_SECONDS:
        del _store[display_id]
        return None
    return group


def cleanup_expired() -> int:
    """Evict all expired display groups.  Returns count of removed entries."""
    now = time.time()
    expired_ids = [
        did for did, group in _store.items()
        if now - group.created_at > TTL_SECONDS
    ]
    for did in expired_ids:
        del _store[did]
    if expired_ids:
        logger.debug("cleanup_expired: removed %d expired displays", len(expired_ids))
    return len(expired_ids)
