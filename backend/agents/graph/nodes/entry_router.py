"""
entry_router node — LangGraph node for fast-path intent classification.

This node absorbs routing_model.py logic into the graph itself.
It classifies user_query into one of 5 intents and returns a Command
that dynamically routes to the correct downstream node.

Architecture:
  1. Fast path: Jaccard token similarity against intent descriptions
  2. Safe degrade: when fast confidence < threshold, default to "chat"
  3. Floor enforcement: confidence < 0.3 → force "chat"
"""

import logging
import re
from typing import Optional

from langgraph.types import Command

from ..state import AgentState

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

INTENTS: list[str] = ["search", "recommend", "order", "analytics", "chat"]

INTENT_DESCRIPTIONS: dict[str, str] = {
    "search":    "find products, search catalog, look up items, browse inventory, keyword search, "
                 "搜索 查找 寻找 商品 产品 浏览 关键词 搜一下 找一下",
    "recommend": "get recommendations, suggest products, personalized picks, what should I buy, trending, popular, similar, for you, "
                 "推荐 建议 热门 流行 趋势 相似 类似 为你 帮我选 买什么",
    "order":     "check order status, cancel order, refund, return, track shipment, order detail, purchase history, "
                 "订单 查询 取消 退款 退货 物流 跟踪 已购买 购买记录",
    "analytics": "weekly report, analytics, statistics, performance, metrics report, data summary, revenue, sales report, "
                 "报告 统计 分析 数据 营收 销售 周报 报表 指标 性能",
    "chat":      "general conversation, chitchat, help, how are you, small talk, greetings, thank you, hello, hi, "
                 "你好 谢谢 再见 聊天 帮助 打招呼",
}

FAST_CONFIDENCE_THRESHOLD: float = 0.85

# ── Keyword boost tables ───────────────────────────────────────────────

KEYWORD_BOOST: dict[str, list[str]] = {
    "search":    ["search", "find", "look", "show", "product", "item",
                  "catalog", "price", "available", "buy",
                  "搜索", "找", "查找", "搜", "商品", "产品", "有没有",
                  "浏览", "关键词", "搜一下", "找一下", "看看"],
    "recommend": ["recommend", "suggest", "popular", "trending", "best",
                  "top", "pick", "for me", "gift", "like",
                  "推荐", "建议", "热门", "流行", "趋势", "相似",
                  "类似", "为你", "帮我选", "买什么", "礼物", "喜欢"],
    "order":     ["order", "cancel", "refund", "return", "ship", "track",
                  "status", "delivery", "bought", "purchase",
                  "订单", "取消", "退款", "退货", "物流", "跟踪",
                  "快递", "发货", "购买", "已买"],
    "analytics": ["report", "analytics", "statistics", "revenue",
                  "sales report", "weekly", "dashboard", "metrics",
                  "performance", "data",
                  "报告", "统计", "分析", "数据", "营收",
                  "销售", "周报", "报表", "指标", "性能", "仪表盘"],
    "chat":      ["hello", "hi", "hey", "help", "thanks", "bye",
                  "how are you", "what's up", "good morning",
                  "你好", "谢谢", "再见", "帮助", "打招呼",
                  "早", "嗨", "哈喽"],
}


# ── Token helpers ──────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Tokenize: English words + individual CJK characters."""
    tokens = set(re.findall(r"[\u4e00-\u9fff]|\w+", text.lower()))
    # Also add bigrams for Chinese (better matching for multi-char terms)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for i in range(len(cjk_chars) - 1):
        tokens.add(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── Fast classifier ────────────────────────────────────────────────────

# Pre-computed token sets for intent descriptions (module-level cache)
_INTENT_TOKENS: dict[str, set[str]] = {
    intent: _tokenize(desc)
    for intent, desc in INTENT_DESCRIPTIONS.items()
}


def _fast_classify(query: str) -> tuple[str, float]:
    """Fast-path classification via Jaccard similarity + keyword boosting.

    Returns:
        (intent, confidence) — best intent and its normalized confidence.
    """
    query_tokens = _tokenize(query)
    query_lower = query.lower()

    scores: dict[str, float] = {}
    for intent in INTENTS:
        # Base: Jaccard similarity against intent description
        base_score = _jaccard_similarity(query_tokens, _INTENT_TOKENS[intent])

        # Keyword boosting: each matching keyword adds 0.08, capped at 0.24
        keywords = KEYWORD_BOOST.get(intent, [])
        keyword_hits = sum(1 for kw in keywords if kw in query_lower)
        boost = min(keyword_hits * 0.08, 0.24)

        scores[intent] = base_score + boost

    # Normalize to [0, 1]
    total = sum(scores.values())
    if total > 0:
        scores = {k: v / total for k, v in scores.items()}

    best_intent = max(scores, key=scores.get)  # type: ignore[arg-type]
    confidence = scores[best_intent]
    return best_intent, confidence


# ── Entry Router Node ──────────────────────────────────────────────────

def entry_router(state: AgentState) -> Command:
    """Entry router node — classifies intent and routes dynamically.

    Fast-path routing with safe degrade:
      1. Jaccard token similarity (always first)
      2. Safe degrade: when confidence < threshold, default to "chat"

    Floor enforcement: if final confidence < 0.3, force "chat".

    Returns:
        Command(goto=intent, update={intent, confidence, routing_method, current_node})
    """
    # State Router preset: accept intent from Layer 0
    # entry_router is an EXECUTOR — must not override state_router's decision.
    preset = state.control_context.get("preset_intent", "")
    if preset in ("search", "recommend", "order", "analytics", "chat"):
        return Command(
            goto=preset,
            update={
                "intent": preset,
                "confidence": 0.9,
                "routing_method": "preset",
                "current_node": "entry_router",
                "ui_message": f"匹配到「{preset}」意图（路由预设）",
            },
        )

    # ConstraintParser override
    # When orchestrator set _search_plan via ConstraintParser, use its intent
    # directly instead of running Jaccard classification.
    search_plan = state.parallel_results.get("_search_plan")
    if search_plan:
        intent = search_plan.get("intent", "chat")
        # Only trust ConstraintParser for definitive intents.
        # "ambiguous" means no structured constraints detected →
        # fall through to Jaccard classifier below.
        if intent != "ambiguous":
            NODE_MAP = {"sort": "search", "recommend": "recommend"}
            goto = NODE_MAP.get(intent, intent)
            if goto not in ("search", "recommend", "chat", "order", "analytics"):
                goto = "chat"
            return Command(
                goto=goto,
                update={
                    "intent": goto,
                    "confidence": 0.95,
                    "routing_method": "constraint_parser",
                    "current_node": "entry_router",
                    "ui_message": f"匹配到「{intent}」意图（约束解析）",
                },
            )

    # ── P3: Session memory check for follow-up answers ──
    from agents.graph.session_memory import get as get_session_memory, collect_answer

    session_mem = get_session_memory(state.session_id)
    if session_mem and session_mem.pending_intent:
        # This is a follow-up answer to a previous clarify question.
        # Skip intent classification — route directly to pending intent.
        if session_mem.missing_slots:
            # The user's query IS the answer (e.g. clicked "1000-3000")
            # Try to match it to a missing slot
            for slot_key in session_mem.missing_slots:
                collect_answer(state.session_id, slot_key, state.user_query)
        return Command(
            goto=session_mem.pending_intent,
            update={
                "intent": session_mem.pending_intent,
                "confidence": 1.0,
                "routing_method": "session",
                "current_node": "entry_router",
                "clarify_round": 1,
                "ui_message": f"继续「{session_mem.pending_intent}」流程…",
            },
        )

    query = state.user_query
    history = state.history if hasattr(state, "history") else []

    # ── Tier 1: Fast path ──
    fast_intent, fast_confidence = _fast_classify(query)

    # Phase B-3: dynamic threshold from RoutingTuner
    from agents.graph.routing.tuner import get_threshold, record_routing
    current_threshold = get_threshold()

    if fast_confidence >= current_threshold:
        logger.debug(
            "Fast router: intent=%s, confidence=%.2f, method=fast",
            fast_intent, fast_confidence,
        )
        intent = fast_intent
        confidence = fast_confidence
        method = "fast"
    else:
        # ── Safe degrade ──
        # entry_router is an EXECUTOR, not a decision-maker.
        # state_router is the sole routing authority.
        # Low-confidence → default to "chat".
        logger.info(
            "Fast router confidence %.2f < %.2f, degrading to chat",
            fast_confidence, current_threshold,
        )
        intent = "chat"
        confidence = max(fast_confidence, 0.3)
        method = "fast_degraded"

    # ── Floor enforcement ──
    if confidence < 0.3:
        logger.warning(
            "Confidence %.2f below floor 0.3, forcing 'chat'", confidence
        )
        intent = "chat"
        confidence = 0.3

    # ── Phase B-3: Record routing decision for tuning ──
    try:
        record_routing(
            session_id=state.session_id,
            intent=intent,
            fast_confidence=fast_confidence,
            routing_method=method,
        )
    except Exception:
        pass

    # ── Return Command with dynamic goto ──
    return Command(
        goto=intent,
        update={
            "intent": intent,
            "confidence": confidence,
            "routing_method": method,
            "current_node": "entry_router",
            "ui_message": f"匹配到「{intent}」意图（置信度 {int(confidence*100)}%）",
        },
    )
