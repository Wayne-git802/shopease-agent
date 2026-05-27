# CONTRACT: IntentClassifier ONLY outputs semantic category.
# It does NOT extract constraints, budget, or sort.
# It does NOT decide routing.

"""
commerce_intent.py — Layer 1 IntentClassifier for fine-grained commerce intents.

Classifies a commerce-level query into one of four sub-intents:
  search, recommend, order, analytics.

Pure rules-based, no LLM, no embeddings.
Weighted signal scoring with competition penalty and additive product-noun boost.
"""

from dataclasses import dataclass

# ════════════════════════════════════════════════════════════════════
# Configuration
# ════════════════════════════════════════════════════════════════════

CONFIDENCE_CONFIG = {
    "chat_fallback": 0.3,       # below this → fallback to chat
    "low_confidence": 0.5,      # below this → low confidence marker
}
SIGNALS_VERSION = "v2"

# ════════════════════════════════════════════════════════════════════
# Weight map
# ════════════════════════════════════════════════════════════════════

_WEIGHTS: dict[str, float] = {
    "strong": 0.35,
    "medium": 0.20,
    "weak": 0.12,
}

# ════════════════════════════════════════════════════════════════════
# Signal keywords — three weight levels per intent
# ════════════════════════════════════════════════════════════════════

SIGNALS: dict[str, dict[str, set[str]]] = {
    "search": {
        "strong": {"搜索", "查找", "搜一下", "找一下", "search", "find"},
        "medium": {"价格", "多少钱", "排序", "筛选", "price", "sort", "便宜", "贵", "cheap", "expensive", "最便宜", "最贵"},
        "weak":   {"找", "看看", "浏览", "有没有", "搜", "browse", "买", "购买", "想买", "性价比", "划算"},
    },
    "recommend": {
        "strong": {"推荐", "建议", "帮我选", "买什么", "recommend", "suggest"},
        "medium": {"礼物", "热门", "流行", "适合", "gift", "popular", "我想买", "我要买"},
        "weak":   {"哪个好", "选哪个", "怎么样", "帮我挑", "推荐一下", "买", "购买"},
    },
    "cart": {
        "strong": {"加入购物车", "加购", "加购物车", "add to cart"},
        "medium": {"购物车", "看看购物车", "cart", "view cart", "先存着", "收藏"},
        "weak":   {"存起来", "先留着", "先加进去"},
    },
    "order": {
        "strong": {"订单", "退款", "退货", "物流", "order", "refund", "return"},
        "medium": {"物流", "取消", "发货", "track", "cancel", "下单", "买了"},
        "weak":   {"查", "查询", "状态", "status", "买", "购买"},
    },
    "analytics": {
        "strong": {"报告", "统计", "分析", "report", "analytics", "statistics"},
        "medium": {"营收", "销售", "指标", "revenue", "metrics"},
        "weak":   {"周报", "月报", "dashboard", "报表"},
    },
    "purchase": {
        "strong": {"下单", "结账", "checkout", "purchase", "买第一个", "买这个", "buy first", "buy this"},
        "medium": {"购买", "买它", "就这个"},
        "weak":   {"买", "buy", "买了"},
    },
}

# ════════════════════════════════════════════════════════════════════
# Product nouns — triggers additive confidence boost
# ════════════════════════════════════════════════════════════════════

PRODUCT_NOUNS: set[str] = {
    "耳机", "手机", "电脑", "笔记本", "键盘", "鼠标", "显示器",
    "平板", "手表", "相机", "音箱", "鞋", "衣服", "包",
    "headphone", "phone", "laptop", "keyboard", "mouse",
    "monitor", "tablet", "watch", "camera", "speaker", "shoe", "bag",
}

# ════════════════════════════════════════════════════════════════════
# Dataclass
# ════════════════════════════════════════════════════════════════════

@dataclass
class IntentResult:
    intent: str        # "search"|"recommend"|"order"|"analytics"
    confidence: float  # 0.0-1.0
    fallback: str      # "chat"
    version: str = "v1"

# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def has_product_noun(query: str) -> bool:
    """Return True if the query contains any known product noun."""
    query_lower = query.lower()
    return any(noun in query_lower for noun in PRODUCT_NOUNS)

# ════════════════════════════════════════════════════════════════════
# Core classifier
# ════════════════════════════════════════════════════════════════════

def classify(query: str) -> IntentResult:
    """Classify a commerce query into a fine-grained intent.

    Returns an IntentResult with intent, confidence, and fallback.
    Pure rules — no LLM, no embeddings.
    """
    query_lower = query.lower()

    # ── 1. Sum weighted signal matches per intent ──
    scores: dict[str, float] = {}
    for intent_name, signal_groups in SIGNALS.items():
        total = 0.0
        for level_name, keywords in signal_groups.items():
            weight = _WEIGHTS[level_name]
            for kw in keywords:
                if kw in query_lower:
                    total += weight
        scores[intent_name] = total

    # ── 2. Zero-signal fallback ──
    if all(s == 0.0 for s in scores.values()):
        return IntentResult(intent="search", confidence=0.0, fallback="chat")

    # ── 3. Determine best and second-best ──
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_best_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # ── 4. Cap raw score at 0.95 ──
    best_score = min(best_score, 0.95)

    # ── 5. Multi-intent competition penalty ──
    if second_best_score > 0.3:
        best_score -= 0.15
        if best_score < 0.0:
            best_score = 0.0

    # ── 6. Additive product-noun boost (conditional floor) ──
    # Product noun + any signal = commerce intent is real, boost confidence.
    if has_product_noun(query) and best_score > 0:
        boost = max(0.18, 0.10 * best_score)
        best_score = min(best_score + boost, 0.95)

    # ── 7. No concrete product → conversation, not execution ──
    # "推荐礼物" has intent but no specific category → lower confidence
    # so ResponsePolicy routes to llm_direct (dialogue) instead of graph.
    if best_intent in ("search", "recommend") and not has_product_noun(query):
        best_score *= 0.5

    return IntentResult(
        intent=best_intent,
        confidence=best_score,
        fallback="chat",
    )
