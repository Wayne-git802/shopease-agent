"""
Intent Parser — classify purchase query into intent + extract reference.

Pure rules. Outputs product reference (index/name) for downstream resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class PurchaseIntent:
    BUY_FIRST = "buy_first"       # "买第一个"
    BUY_THIS  = "buy_this"        # "买这个"
    CHECKOUT  = "checkout"        # "下单" / "结账"
    CONFIRM   = "confirm"         # "确认" / "买"
    DECLINE   = "decline"         # "算了"
    OTHER     = "other"           # fallback


_INTENT_KEYWORDS: dict[str, list[str]] = {
    PurchaseIntent.BUY_FIRST: ["买第一个", "买第1", "第一个下单", "buy first", "第一个买了"],
    PurchaseIntent.BUY_THIS:  ["买这个", "买它", "buy this", "就这个"],
    PurchaseIntent.CHECKOUT:  ["下单", "结账", "购买", "checkout", "buy", "purchase", "买"],
    PurchaseIntent.CONFIRM:   ["确认", "是的", "对", "可以", "yes", "ok", "confirm"],
    PurchaseIntent.DECLINE:   ["算了", "不用", "不要", "不了", "no", "cancel"],
}

_REFERENCE_PATTERNS = [
    (["第一个", "第1", "1st"], "index", 0),
    (["第二个", "第2", "2nd"], "index", 1),
    (["第三个", "第3", "3rd"], "index", 2),
]


@dataclass
class ParsedIntent:
    intent: str                          # PurchaseIntent value
    reference_type: str | None = None    # "index" | "name" | None
    reference_value: str | int | None = None
    confidence: float = 0.8


def parse(query: str) -> ParsedIntent:
    """Parse user query into a purchase intent."""
    q = query.lower().strip()

    # 1. Check reference patterns
    for keywords, ref_type, ref_val in _REFERENCE_PATTERNS:
        for kw in keywords:
            if kw in q:
                return ParsedIntent(
                    intent=PurchaseIntent.BUY_FIRST,
                    reference_type=ref_type,
                    reference_value=ref_val,
                    confidence=0.9,
                )

    # 2. Check intent keywords (first match wins)
    for intent_name, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                return ParsedIntent(intent=intent_name, confidence=0.85)

    # 3. Fallback
    return ParsedIntent(intent=PurchaseIntent.OTHER, confidence=0.3)
