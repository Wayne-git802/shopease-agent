"""
Intent Parser — classify order query into intent + extract references.

Pure rules, no LLM, no DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class OrderIntent:
    QUERY_ORDERS   = "query_orders"     # 查订单
    ORDER_DETAIL   = "order_detail"     # 查看详情
    REFUND         = "refund"           # 退款
    CANCEL         = "cancel"           # 取消订单
    LOGISTICS      = "logistics"        # 查物流
    CONFIRM        = "confirm"          # 确认（退款/取消）
    DECLINE        = "decline"          # 算了/不退了
    REFERENCE      = "reference"        # "第二个" / "那个退款的"
    OTHER          = "other"            # 回退到 CommerceAgent


# Keywords per intent (ordered by specificity)
_INTENT_KEYWORDS: dict[str, list[str]] = {
    OrderIntent.REFUND:    ["退款", "退", "refund"],
    OrderIntent.CANCEL:    ["取消订单", "取消", "cancel order", "cancel"],
    OrderIntent.LOGISTICS: ["物流", "快递", "到哪", "发货", "logistics", "tracking", "track"],
    OrderIntent.CONFIRM:   ["确认", "是的", "对", "退吧", "可以", "yes", "ok", "confirm"],
    OrderIntent.DECLINE:   ["算了", "不用", "不要", "不了", "no", "cancel", "decline"],
    OrderIntent.QUERY_ORDERS: ["查订单", "我的订单", "订单列表", "订单", "order", "orders", "买了什么"],
    OrderIntent.ORDER_DETAIL: ["详情", "detail"],
}

# Reference patterns
_REFERENCE_PATTERNS = [
    (["第二个", "第2", "2nd"], "index", 1),       # 1-indexed
    (["第一个", "第1", "1st"], "index", 0),
    (["第三个", "第3", "3rd"], "index", 2),
    (["那个退款", "退款的"], "match", "refund"),
    (["最新的", "最近"], "match", "latest"),
]


@dataclass
class ParsedIntent:
    intent: str                          # OrderIntent value
    is_reference: bool = False
    reference_type: str | None = None    # "index" | "match"
    reference_value: str | int | None = None
    confidence: float = 0.8


def parse(query: str) -> ParsedIntent:
    """Parse user query into an order intent."""
    q = query.lower().strip()

    # 1. Check reference patterns first
    for keywords, ref_type, ref_val in _REFERENCE_PATTERNS:
        for kw in keywords:
            if kw in q:
                return ParsedIntent(
                    intent=OrderIntent.REFERENCE,
                    is_reference=True,
                    reference_type=ref_type,
                    reference_value=ref_val,
                    confidence=0.9,
                )

    # 2. Check intent keywords (first match wins)
    for intent_name, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                return ParsedIntent(intent=intent_name, confidence=0.85)

    # 3. Short ambiguous → other (let CommerceAgent handle)
    return ParsedIntent(intent=OrderIntent.OTHER, confidence=0.3)
