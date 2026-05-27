"""
Input Guard — routing pre-layer arbitration.

Runs BEFORE ConstraintParser. Classifies query into one of three
routing signals: "chat", "search", "recommend".

Key design decisions:
  - Safe default is "chat" (never assume purchase intent)
  - "ambiguous" is a signal, not a type — always resolved here
  - Zero LLM calls — pure regex + keyword matching

Usage:
    from agents.graph.nodes.input_guard import classify

    signal = classify("hello")
    # → "chat"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

RoutingSignal = Literal["chat", "search", "recommend"]


# ═══════════════════════════════════════════════════════════════
# Conversation Signals — contextual modifiers
# ═══════════════════════════════════════════════════════════════

@dataclass
class ConversationSignals:
    """Contextual conversation signals detected from query structure.
    
    Strengths are floats (0.0–1.0) for future weak-signal support.
    Currently 0.0 or 1.0, but interface allows gradual values.
    """
    capability: float = 0.0         # "你能推荐吗"
    stop: float = 0.0               # "别推荐了" "算了"
    ack: float = 0.0                # "嗯嗯" "好的"
    negative_feedback: float = 0.0  # "不推荐这个"

    def any_signal(self) -> bool:
        return any([
            self.capability > 0, self.stop > 0,
            self.ack > 0, self.negative_feedback > 0,
        ])

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "stop": self.stop,
            "ack": self.ack,
            "negative_feedback": self.negative_feedback,
        }


@dataclass
class ScoreAdjustment:
    """A single signal → score adjustment, for trace/debug."""
    signal: str
    delta: float


@dataclass 
class IntentScore:
    """Final intent score with full adjustment chain preserved."""
    intent: str
    base_confidence: float
    adjusted_confidence: float
    adjustments: list[ScoreAdjustment] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "base_confidence": round(self.base_confidence, 3),
            "adjusted_confidence": round(self.adjusted_confidence, 3),
            "adjustments": [
                {"signal": a.signal, "delta": round(a.delta, 3)}
                for a in self.adjustments
            ],
        }


# ═══════════════════════════════════════════════════════════════
# Chat patterns — clearly non-shopping queries
# ═══════════════════════════════════════════════════════════════

CHAT_PATTERNS: list[str] = [
    # Greetings
    r"^(hi|hey|hello|yo|sup|good\s*(morning|afternoon|evening|night))\b",
    r"^(你好|嗨|哈喽|早|晚上好|下午好|在吗|在不在)",
    r"^(thanks|thank\s*you|thx|ty)\b",
    r"^(谢谢|多谢|感谢|谢了)",
    r"^(bye|goodbye|see\s*you|cya|later)\b",
    r"^(再见|拜拜|回头见|下次见)",
    # Self-referential
    r"(你是谁|你叫什么|你的名字|who\s*are\s*you|what\s*is\s*your\s*name)",
    r"(你能做什么|你能干嘛|what\s*can\s*you\s*do|你的功能|help\s*me)",
    r"(你是.*AI|你是.*机器人|are\s*you.*(ai|bot|robot))",
    # Meta / how-to
    r"(怎么用|如何使用|how\s*to\s*use|教程|tutorial|guide)",
    r"(功能.*介绍|feature.*list|有什么功能)",
    # Pure small talk
    r"^(how\s*are\s*you|what'?s?\s*up|how'?s?\s*it\s*going)",
    r"^(你.*怎么样|最近.*怎么样|今天.*怎么样)",
    r"^(test|testing|测试|试试|试一下)$",
    r"^(讲个笑话|说个笑话|tell\s*.*joke|joke)",
    # Non-shopping intent
    r"(天气|weather|temperature|forecast)",
    r"(时间|what\s*time|current\s*time|date\s*today)",
    r"(新闻|news|headline)",
]

# ── Chat keyword boost (presence lowers recommend/search score) ──
CHAT_KEYWORDS: set[str] = {
    "hello", "hi", "hey", "你好", "谢谢", "再见", "bye", "thanks",
    "你是谁", "who are you", "help", "帮助", "怎么用", "how to",
    "test", "测试", "试一下", "joke", "笑话", "天气", "weather",
}


# ═══════════════════════════════════════════════════════════════
# Search patterns — structured queries with sort/filter intent
# ═══════════════════════════════════════════════════════════════

SEARCH_PATTERNS: list[str] = [
    # Sort keywords
    r"(cheapest|most\s*expensive|lowest\s*price|highest\s*price)",
    r"(最便宜|最贵|最低价|最高价|价格最低|价格最高)",
    r"(top\s*rated|highest\s*rated|best\s*rated|most\s*popular)",
    r"(评分最高|评价最好|销量最高|最受欢迎)",
    r"(price.*(low|high|asc|desc)|sort\s*by\s*price)",
    r"(按价格|按销量|按评分|排序)",
    r"(under\s*\d+|below\s*\d+|within\s*\d+|budget\s*\d+)",
    r"(\d+以内|\d+以下|\d+之内|预算\d+)",
    r"(\d+[-~到]\d+)\s*(元|块|块钱)?",
    # Clear search verbs
    r"^(find|search|look\s*for|show\s*me|list|browse)\b",
    r"^(找|搜|搜索|查|看看|浏览|找一下|搜一下)\b",
    r"\b(find|search)\s+(me|for)\b",
    # Category-level browsing (broad — needs explicit "all"/"every" prefix)
    r"^(all|every|全部|所有|每个).*(product|item|商品|产品)",
    r"^(show|list|display|展示|列出|显示).*(all|every|全部|所有)",
    # NOT: raw product nouns (those are handled by PRODUCT_NOUNS → recommend)
]

SEARCH_KEYWORDS: set[str] = {
    "find", "search", "look for", "show me", "browse",
    "找", "搜", "搜索", "查找", "看看", "浏览",
    "cheapest", "most expensive", "最便宜", "最贵",
    "sort", "排序", "filter", "筛选",
}


# ═══════════════════════════════════════════════════════════════
# Recommend patterns — purchase/shopping intent
# ═══════════════════════════════════════════════════════════════

RECOMMEND_PATTERNS: list[str] = [
    # Explicit recommend
    r"(recommend|suggest|pick|choose)",
    r"(推荐|建议|帮我选|买什么|选哪个|哪个好)",
    r"(适合|适合我|for\s*me|for\s*you)",
    # Comparison
    r"(vs\.?|versus|or\b.*\bor\b|对比|比较|哪个更)",
    # Best / popular / trending
    r"(best[-\s]sell(er|ing)|popular|trending|hot|top\s*\d+)",
    r"(热卖|热销|销量.*好|卖.*好|流行|爆款|热销|热卖)",
    # Gift / occasion
    r"(gift|present|礼物|送.*什么|生日|birthday|holiday)",
    # Like / similar
    r"(similar\s*to|like\s*this|something\s*like)",
    r"(类似|相似|像.*一样|差不多的)",
    # Explicit purchase intent
    r"(I\s*want|I\s*need|I'?m\s*looking\s*for|buy)",
    r"(我想买|我要买|我需要|想买|要买|买一个|买个)",
    r"(shopping|购买|购物|下单)",
]

RECOMMEND_KEYWORDS: set[str] = {
    "recommend", "suggest", "best", "popular", "trending",
    "推荐", "建议", "热门", "流行", "帮我选", "买什么",
    "礼物", "gift", "类似", "similar", "对比", "compare",
    "我想买", "我要买", "buy", "purchase", "购买",
}

# ── Product category detection (simple noun-based) ──
PRODUCT_NOUNS: set[str] = {
    "phone", "laptop", "headphone", "earphone", "tablet", "watch",
    "shoe", "sneaker", "boot", "bag", "backpack", "wallet",
    "shirt", "dress", "jacket", "hoodie", "jeans", "pants", "shorts",
    "skirt", "sweater", "t-shirt", "tshirt", "cloth", "服装",
    "camera", "speaker", "keyboard", "mouse", "monitor",
    "手机", "电脑", "笔记本", "耳机", "平板", "手表",
    "鞋", "运动鞋", "靴子", "包", "背包", "钱包", "皮夹",
    "衣服", "裙子", "夹克", "卫衣", "牛仔裤", "裤子", "短裤",
    "衬衫", "毛衣", "T恤",
    "相机", "音箱", "键盘", "鼠标", "显示器", "屏幕",
    "化妆品", "护肤品", "香水", "口红", "精华",
    "食品", "零食", "饮料", "咖啡", "茶",
    "瑜伽垫", "瑜伽", "健身", "运动", "哑铃",
    "玩具", "baby", "婴儿", "儿童", "kids",
    "书", "book", "杂志", "magazine",
    "车", "car", "自行车", "bike", "摩托",
    "家具", "furniture", "灯具", "lamp", "地毯", "rug",
    "吉他", "guitar", "钢琴", "piano",
    "项链", "戒指", "耳环", "珠宝", "jewelry",
}


# ═══════════════════════════════════════════════════════════════
# Main classifier
# ═══════════════════════════════════════════════════════════════

def _normalize(query: str) -> str:
    """Fullwidth→halfwidth, strip, lowercase."""
    result = []
    for ch in query:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            result.append(" ")
        else:
            result.append(ch)
    return " ".join("".join(result).split()).lower()


def _match_any(patterns: list[str], text: str) -> bool:
    """Check if any regex pattern matches the text."""
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _has_nouns(nouns: set[str], text: str) -> bool:
    """Check if any product noun appears in the text."""
    for noun in nouns:
        if noun in text:
            return True
    return False


def classify(query: str) -> RoutingSignal:
    """Classify a user query into 'chat', 'search', or 'recommend'.

    Priority order:
      1. Chat patterns (highest — override everything else)
      2. Search patterns (structured intent)
      3. Recommend patterns (purchase intent)
      4. Product nouns → recommend (implicit purchase intent)
      5. Default → chat (safe fallback)
    """
    if not query or not query.strip():
        return "chat"

    normalized = _normalize(query)
    query_lower = normalized.lower()

    # ── Tier 1: Chat detection ─────────────────────────────────
    # Short queries are almost always chat unless very specific
    if len(query.strip()) <= 3 and not _has_nouns(PRODUCT_NOUNS, query_lower):
        return "chat"

    if _match_any(CHAT_PATTERNS, normalized):
        return "chat"

    # ── Tier 2: Search detection ───────────────────────────────
    if _match_any(SEARCH_PATTERNS, normalized):
        # Reverse check: if query has quality/evaluation words +
        # product nouns, it's really a recommend despite the search verb
        quality_words = {"good", "best", "great", "适合", "好用", "好看", "推荐", "不错"}
        has_quality = any(w in query_lower for w in quality_words)
        has_product = _has_nouns(PRODUCT_NOUNS, query_lower)
        if not (has_quality and has_product):
            return "search"
        # Fall through to Tier 3

    # ── Tier 3: Recommend detection ────────────────────────────
    if _match_any(RECOMMEND_PATTERNS, normalized):
        return "recommend"

    # ── Tier 4: Product noun detection ─────────────────────────
    if _has_nouns(PRODUCT_NOUNS, query_lower):
        return "recommend"

    # ── Tier 5: Score-based fallback ───────────────────────────
    # Count keyword hits for a tie-breaker
    chat_score = sum(1 for kw in CHAT_KEYWORDS if kw in query_lower)
    search_score = sum(1 for kw in SEARCH_KEYWORDS if kw in query_lower)
    recommend_score = sum(1 for kw in RECOMMEND_KEYWORDS if kw in query_lower)

    if recommend_score > search_score and recommend_score > chat_score:
        return "recommend"
    if search_score > chat_score and search_score > recommend_score:
        return "search"

    # ── Default: chat ──────────────────────────────────────────
    # Safe default — never assume purchase intent without evidence
    return "chat"


def is_chat(query: str) -> bool:
    """Quick check: is this a chat/non-shopping query?"""
    return classify(query) == "chat"


def is_search_intent(query: str) -> bool:
    """Quick check: is this a structured search/sort query?"""
    return classify(query) == "search"


def is_purchase_intent(query: str) -> bool:
    """Quick check: is this a purchase/recommend query?"""
    return classify(query) == "recommend"


# ═══════════════════════════════════════════════════════════════
# Conversation Signal Detector
# ═══════════════════════════════════════════════════════════════

# Patterns are deliberately generic — they match on sentence structure,
# not specific commerce keywords. This avoids growing a keyword blacklist.

_CAPABILITY_PATTERNS: list[str] = [
    r"(你能|你可以|你会|你能帮我).{0,6}(吗|么|不)",
    r"(can|could)\s+you.{0,15}\?",
]

_STOP_PATTERNS: list[str] = [
    r"(别|不要|不用|不想).{0,3}(了|啦)",
    r"^(算了|不用了|不要了)$",
]

_ACK_PATTERNS: list[str] = [
    r"^(嗯+|哦+|好[的吧]?|ok|yes|对|是的|可以|行)$",
]

_NEGATIVE_PATTERNS: list[str] = [
    r"(不|别).{0,2}(推荐|建议|喜欢|好|行)",
    r"(这个|那个).{0,2}(不|别).{0,2}(好|行|推荐)",
]


def _has_product_signal(query: str) -> bool:
    """Check if query contains product nouns or price constraints."""
    if _has_nouns(PRODUCT_NOUNS, query.lower()):
        return True
    # Price patterns
    if re.search(r'\d+\s*(元|块|块钱|以内|以下)', query):
        return True
    if re.search(r'(under|below|within)\s*\d+', query.lower()):
        return True
    return False


def detect_conversation_signals(query: str) -> ConversationSignals:
    """Detect conversational signals from query structure.
    
    Pure function — no LLM, no DB, no side effects.
    Returns ConversationSignals with float strengths (0.0 or 1.0).
    """
    if not query or not query.strip():
        return ConversationSignals()
    
    normalized = query.strip()
    has_product = _has_product_signal(query)
    
    signals = ConversationSignals()
    
    # ── Capability question ──
    if any(re.search(p, normalized) for p in _CAPABILITY_PATTERNS):
        # With product → weak signal only
        # Without product → strong "what can you do" question
        signals.capability = 0.3 if has_product else 1.0
    
    # ── Stop action ──
    if any(re.search(p, normalized) for p in _STOP_PATTERNS):
        signals.stop = 1.0
    
    # ── Acknowledgement ──
    if any(re.search(p, normalized) for p in _ACK_PATTERNS):
        signals.ack = 1.0
    
    # ── Negative feedback ──
    if any(re.search(p, normalized) for p in _NEGATIVE_PATTERNS):
        signals.negative_feedback = 0.8
    
    return signals
