"""Cart intent parser — pure keyword-weight rules, no LLM."""

from dataclasses import dataclass
from enum import Enum


class CartIntent(str, Enum):
    ADD_TO_CART = "ADD_TO_CART"
    VIEW_CART = "VIEW_CART"
    REMOVE_FROM_CART = "REMOVE_FROM_CART"
    UPDATE_QTY = "UPDATE_QTY"
    CHECKOUT = "CHECKOUT"
    DECLINE = "DECLINE"


# ── keyword → (intent, weight) ─────────────────────────────────────────────

_KEYWORD_RULES: list[tuple[str, CartIntent, float]] = [
    # strong (0.35)
    ("加购", CartIntent.ADD_TO_CART, 0.35),
    ("加入购物车", CartIntent.ADD_TO_CART, 0.35),
    ("删除", CartIntent.REMOVE_FROM_CART, 0.35),
    ("结算", CartIntent.CHECKOUT, 0.35),
    ("下单", CartIntent.CHECKOUT, 0.35),

    # medium (0.20)
    ("购物车", CartIntent.VIEW_CART, 0.20),
    ("看看", CartIntent.VIEW_CART, 0.20),
    ("买两个", CartIntent.ADD_TO_CART, 0.20),
    ("加一个", CartIntent.ADD_TO_CART, 0.20),

    # weak (0.12)
    ("存起来", CartIntent.ADD_TO_CART, 0.12),
    ("先留着", CartIntent.ADD_TO_CART, 0.12),
    ("不要了", CartIntent.DECLINE, 0.12),
]


# ── public types ───────────────────────────────────────────────────────────

@dataclass
class IntentResult:
    """Returned by `parse()`."""
    intent: str          # CartIntent value as string
    confidence: float    # 0.0 – 1.0
    matched_keywords: list[str]


# ── scoring ────────────────────────────────────────────────────────────────

def parse(query: str) -> IntentResult:
    """Score every intent by weighted keyword matches.  Highest score wins.
    Zero-score → IntentResult(intent='unknown', confidence=0.0, kw=[])."""

    scores: dict[CartIntent, float] = {i: 0.0 for i in CartIntent}
    matched: dict[CartIntent, list[str]] = {i: [] for i in CartIntent}

    for keyword, intent, weight in _KEYWORD_RULES:
        if keyword in query:
            scores[intent] += weight
            matched[intent].append(keyword)

    best_intent = max(scores, key=lambda k: scores[k])
    best_score = scores[best_intent]

    if best_score == 0.0:
        return IntentResult(intent="unknown", confidence=0.0, matched_keywords=[])

    return IntentResult(
        intent=best_intent.value,
        confidence=round(best_score, 4),
        matched_keywords=matched[best_intent],
    )


# ── quick smoke test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [
        "加购这个商品",
        "加入购物车",
        "我要结算",
        "下单吧",
        "看看购物车里有什么",
        "删除那个东西",
        "不要了",
        "买两个苹果",
        "存起来",
        "先留着",
        "你好",
    ]
    for q in cases:
        r = parse(q)
        print(f"{q!r:30s} → {r.intent:<18s} {r.confidence:.2f}  {r.matched_keywords}")
