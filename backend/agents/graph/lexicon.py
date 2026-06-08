"""
lexicon.py — Unified shared product vocabulary for the ShopEase AI Agent.

Single source of truth for:
  PRODUCT_NOUNS          — concrete product nouns (triggers additive confidence)
  CATEGORY_LEXICON       — token → label mapping (category / abstract_goal / descriptor)
  COMMERCE_SIGNAL_WORDS  — coarse commerce-intent signal words for Layer 0 routing

Previously duplicated across:
  - commerce_intent.py  (PRODUCT_NOUNS)
  - grounding.py        (ProductLexicon)
  - state_router.py     (_KEYWORDS["commerce"])
"""

# ════════════════════════════════════════════════════════════════════
# PRODUCT_NOUNS — concrete product nouns for commerce-intent detection
# Authoritative source: commerce_intent.py, merged with grounding.py categories
# ════════════════════════════════════════════════════════════════════

PRODUCT_NOUNS: set[str] = {
    # --- From commerce_intent.py (authoritative baseline) ---
    "耳机", "手机", "电脑", "笔记本", "键盘", "鼠标", "显示器",
    "平板", "手表", "相机", "音箱", "鞋", "衣服", "包",
    "headphone", "phone", "laptop", "keyboard", "mouse",
    "monitor", "tablet", "watch", "camera", "speaker", "shoe", "bag",

    # --- Merged from grounding.py category tokens (not in commerce_intent) ---
    "充电器", "数据线", "移动电源", "充电宝",
    "鞋子", "帽子", "围巾", "眼镜", "首饰", "项链",
    "口红", "香水", "护肤品", "化妆品", "面膜", "洗面奶",
    "椅子", "桌子", "台灯", "杯子", "枕头", "被子", "锅",
    "球", "球拍", "瑜伽垫", "哑铃",
    "书", "本子", "笔",
    "零食", "茶叶", "咖啡",
    "headphones", "shoes", "perfume", "chair", "lamp", "book",
}

# ════════════════════════════════════════════════════════════════════
# CATEGORY_LEXICON — token → label mapping
# Authoritative source: grounding.py ProductLexicon, merged with commerce_intent extras
#
# Labels:
#   "category"      — concrete product anchor, searchable
#   "abstract_goal" — high-intent but broad, needs refinement but still searchable
#   "descriptor"    — quality/popularity word, no anchor value
# ════════════════════════════════════════════════════════════════════

CATEGORY_LEXICON: dict[str, str] = {
    # --- categories (from grounding.py) ---
    "耳机": "category", "手机": "category", "电脑": "category", "平板": "category",
    "键盘": "category", "鼠标": "category", "显示器": "category", "音箱": "category",
    "相机": "category", "手表": "category", "充电器": "category", "数据线": "category",
    "移动电源": "category", "充电宝": "category",
    "衣服": "category", "鞋子": "category", "包": "category", "帽子": "category",
    "围巾": "category", "眼镜": "category", "首饰": "category", "项链": "category",
    "口红": "category", "香水": "category", "护肤品": "category", "化妆品": "category",
    "面膜": "category", "洗面奶": "category",
    "椅子": "category", "桌子": "category", "台灯": "category", "杯子": "category",
    "枕头": "category", "被子": "category", "锅": "category",
    "球": "category", "球拍": "category", "瑜伽垫": "category", "哑铃": "category",
    "书": "category", "本子": "category", "笔": "category",
    "零食": "category", "茶叶": "category", "咖啡": "category",
    "headphones": "category", "phone": "category", "laptop": "category",
    "keyboard": "category", "mouse": "category", "monitor": "category",
    "watch": "category", "camera": "category", "speaker": "category",
    "shoes": "category", "bag": "category", "perfume": "category",
    "chair": "category", "lamp": "category", "book": "category",

    # --- Merged from commerce_intent.py (not in grounding.py ProductLexicon) ---
    "笔记本": "category",
    "tablet": "category",

    # --- abstract goals ---
    "礼物": "abstract_goal", "送人": "abstract_goal", "送礼": "abstract_goal",
    "好东西": "abstract_goal", "值得买": "abstract_goal",
    "送女友": "abstract_goal", "送男朋友": "abstract_goal",
    "送爸妈": "abstract_goal", "送朋友": "abstract_goal", "送孩子": "abstract_goal",
    "gift": "abstract_goal", "present": "abstract_goal",

    # --- descriptors ---
    "好看": "descriptor", "好用": "descriptor", "流行": "descriptor",
    "热门": "descriptor", "爆款": "descriptor", "新款": "descriptor", "新出": "descriptor",
    "可爱": "descriptor", "酷": "descriptor", "时尚": "descriptor",
    "高级": "descriptor", "简约": "descriptor", "实用": "descriptor",
    "耐用": "descriptor", "舒服": "descriptor", "轻便": "descriptor",
    "高端": "descriptor", "性价比高": "descriptor",
}

# ════════════════════════════════════════════════════════════════════
# COMMERCE_SIGNAL_WORDS — coarse commerce-intent signal words
# Authoritative source: state_router.py _KEYWORDS["commerce"]
# Used by Layer 0 router for initial intent classification
# ════════════════════════════════════════════════════════════════════

COMMERCE_SIGNAL_WORDS: set[str] = {
    "搜索", "找", "推荐", "买", "耳机", "手机", "电脑", "订单", "退款",
    "物流", "取消", "发货", "价格", "送", "礼物", "送礼", "加购", "购物车",
    "recommend", "search", "buy", "order", "refund", "track", "cancel",
    # Explore / open-ended browsing
    "好看", "好用", "流行", "热门", "爆款", "热销", "新款", "新出",
    "有什么", "有没有", "值得", "划算", "推荐", "逛逛", "看看", "浏览",
    "建议", "性价比", "帮选", "帮我", "哪个好", "怎么样", "选哪个",
    "适合", "适合我", "学生党", "送女友", "送男朋友", "便宜",
}
