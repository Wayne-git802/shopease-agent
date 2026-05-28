"""
state_router.py — Layer 0 Single Routing Authority for the ShopEase AI Agent.

Three-layer design replacing Input Guard + Preprocessor routing:
  Layer 1 — Intent Classifier   (pure text, NEVER looks at session)
  Layer 2 — Context Resolver    (fills missing args, NEVER changes intent)
  Layer 3 — Policy Engine       (decides execution path + cost profile)

state_router is the SOLE routing authority — it alone decides intent and path.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════

GREETING_REPLIES: dict[str, list[str]] = {
    "greeting": ["你好！有什么可以帮你？", "嗨！需要找什么商品吗？", "在的！想买什么？"],
    "ack_complete": ["好的，还有需要帮忙的吗？", "没问题，随时找我。"],
    "unclear": ["抱歉，我没有理解你的意思。请换个说法试试？"],
}

_KEYWORDS: dict[str, set[str]] = {
    "greeting": {"hello", "hi", "hey", "你好", "您好", "嗨", "在吗", "早", "晚上好",
                 "哈喽", "哈啰", "哈罗", "good morning", "good evening"},
    "chat": {"thanks", "谢谢", "不用了", "你是谁", "天气", "新闻", "test", "测试",
             "how are you", "what can you do", "怎么用"},
    "commerce": {"搜索", "找", "推荐", "买", "耳机", "手机", "电脑", "订单", "退款",
                 "物流", "取消", "发货", "价格", "送", "礼物", "送礼", "加购", "购物车",
                 "recommend", "search", "buy", "order", "refund", "track", "cancel",
                 # Explore / open-ended browsing
                 "好看", "好用", "流行", "热门", "爆款", "热销", "新款", "新出",
                 "有什么", "有没有", "值得", "划算", "推荐", "逛逛", "看看", "浏览",
                 "建议", "性价比", "帮选", "帮我", "哪个好", "怎么样", "选哪个",
                 "适合", "适合我", "学生党", "送女友", "送男朋友", "便宜"},
}

SESSION_TTL_SECONDS: int = 1800  # 30 minutes

# ════════════════════════════════════════════════════════════════════
# RouteDecision Dataclass
# ════════════════════════════════════════════════════════════════════

@dataclass
class RouteDecision:
    """Single routing decision. state_router is the sole producer."""
    intent: str = "chat"                # greeting|chat|ack_resolve|commerce|unclear
    confidence: float = 0.0
    reason: str = ""                    # human-readable routing reason
    candidates: list[str] = field(default_factory=list)
    resolved_query: str | None = None   # pure text, NO control signals
    control_context: dict = field(default_factory=dict)
    execution_hint: str = "lightweight" # trivial|lightweight|full_graph
    needs_commerce_layer: bool = False  # True → orchestrator invokes Layer 1
    needs_llm: bool = False
    needs_db: bool = False

# ════════════════════════════════════════════════════════════════════
# Safety Layer — runs BEFORE any routing decision
# ════════════════════════════════════════════════════════════════════

def _is_session_stale(session: object | None,
                      ttl_seconds: int = SESSION_TTL_SECONDS) -> bool:
    """True if session.last_updated is None or older than TTL."""
    if session is None:
        return True
    lu = getattr(session, "last_updated", None)
    if lu is None:
        return True
    now = datetime.now(timezone.utc)
    delta = ((now.replace(tzinfo=None) - lu).total_seconds()
             if lu.tzinfo is None else (now - lu).total_seconds())
    return delta > ttl_seconds


def _resolve_conflict(candidates: list[str],
                      session: object | None = None) -> str:
    """Resolve ambiguity: context-dependent intents > commerce > fallback chat."""
    if len(candidates) <= 1:
        return candidates[0] if candidates else "chat"
    for group in (["ack_resolve", "clarify"],
                  ["commerce", "search", "recommend"],
                  ["greeting", "chat"]):
        for intent in group:
            if intent in candidates:
                return intent
    return "chat"


# ════════════════════════════════════════════════════════════════════
# Layer 1 — Intent Classifier (pure text, NEVER looks at session)
# ════════════════════════════════════════════════════════════════════

# Conversational fillers — must NOT be mistaken for gibberish
_CONVERSATIONAL: set[str] = {"嗯", "啊", "哦", "好", "行", "对", "哈", "哎", "诶", "嗨", "在", "不", "可", "没", "有", "是", "您", "请"}


def _is_gibberish(query: str) -> bool:
    """Detect repetitive/hollow input with no semantic value."""
    q = query.strip()
    # Empty or pure non-CJK
    if not q:
        return True
    # 2+ chars, 2 or fewer unique → repetitive like "呃呃"
    if len(q) >= 2 and len(set(q)) <= 2:
        if q[0] not in _CONVERSATIONAL:
            return True
    return False


def _classify_intent(query: str) -> dict:
    """Classify query into one of 4 coarse intents: greeting|chat|commerce|unclear.

    Confidence: one-category match → 0.9; multi-match → weighted by hits;
    no match → unclear/0.5.
    """
    query_lower = query.lower()
    hits: dict[str, int] = {}
    for category, keywords in _KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in query_lower)
        if count > 0:
            hits[category] = count

    candidates = list(hits.keys())
    if not candidates:
        # Gibberish detection: repetitive chars with no semantic content
        if _is_gibberish(query):
            return {"intent": "unclear", "confidence": 0.0, "candidates": []}
        # Fallback: short text with no commerce signal → likely social opener
        q = query_lower
        commerce_kw = _KEYWORDS.get("commerce", set())
        if len(q) <= 4 and not any(kw in q for kw in commerce_kw):
            return {"intent": "greeting", "confidence": 0.6, "candidates": []}
        return {"intent": "unclear", "confidence": 0.5, "candidates": []}
    if len(candidates) == 1:
        return {"intent": candidates[0], "confidence": 0.9, "candidates": candidates}

    # Multiple categories → weighted confidence
    total = sum(hits.values())
    best = max(hits, key=hits.get)  # type: ignore[arg-type]
    confidence = round(0.5 + 0.35 * hits[best] / total, 2)
    return {"intent": best, "confidence": confidence, "candidates": candidates}


# ════════════════════════════════════════════════════════════════════
# Layer 2 — Context Resolver (fills missing args, NEVER changes intent)
# ════════════════════════════════════════════════════════════════════

def _has_strong_intent(query: str) -> bool:
    """True if query has commerce keywords → user changed topic, don't force old slots."""
    commerce_kw = _KEYWORDS.get("commerce", set())
    query_lower = query.lower()
    return any(kw in query_lower for kw in commerce_kw)


def _needs_resolve(query: str, session: object | None, raw_intent: str) -> bool:
    """True when session has pending_slots + query is short + no topic change."""
    if session is None:
        return False
    pending_slots = getattr(session, "pending_slots", None)
    if not pending_slots:
        return False
    if _has_strong_intent(query):
        return False  # user changed topic
    return len(query.strip()) < 10


def _resolve(query: str, session: object) -> tuple[str | None, dict]:
    """Fill pending slots. Returns (resolved_query, control_context).

    resolved_query is pure text — NO control signals like "[确认]".
    """
    ctx: dict = {
        "resolved_slots": {},
        "original_query": query,
        "active_domain": getattr(session, "active_domain", None),
    }
    pending_slots = getattr(session, "pending_slots", None) or {}
    if not pending_slots:
        return query, ctx

    # Fill first unfilled slot
    for slot_key in list(pending_slots.keys()):
        if not pending_slots[slot_key]:
            ctx["resolved_slots"][slot_key] = query.strip()
            pending_slots[slot_key] = query.strip()
            break

    # Build resolved query (pure text, no control signals)
    parts = [query.strip()] + [f"{k}:{v}" for k, v in ctx["resolved_slots"].items()]
    resolved_query = " ".join(parts)

    pq = getattr(session, "pending_question", None)
    if pq:
        ctx["pending_question"] = pq
    return resolved_query, ctx


# ════════════════════════════════════════════════════════════════════
# Layer 3 — Policy Engine (decides path + cost profile)
# ════════════════════════════════════════════════════════════════════

_EXECUTION_MAP: dict[str, tuple[str, bool, bool, bool]] = {
    # intent → (execution_hint, needs_llm, needs_db, needs_commerce_layer)
    "greeting":    ("trivial",      False, False, False),
    "chat":        ("lightweight",  True,  False, False),
    "commerce":    ("full_graph",   True,  True,  True),
    "ack_resolve": ("full_graph",   True,  True,  True),
    "unclear":     ("lightweight",  True,  False, False),
}


def _plan_execution(raw_intent: str,
                    control_context: dict | None = None) -> tuple[str, bool, bool, bool]:
    """Map resolved intent to (execution_hint, needs_llm, needs_db, needs_commerce_layer)."""
    ctx = control_context or {}
    if ctx.get("resolved_slots") or raw_intent == "ack_resolve":
        return ("full_graph", True, True, True)
    return _EXECUTION_MAP.get(raw_intent, ("lightweight", True, False, False))


# ════════════════════════════════════════════════════════════════════
# Template helpers
# ════════════════════════════════════════════════════════════════════

def _pick_template(intent: str) -> str:
    """Random template reply for greeting/ack intents."""
    pool = GREETING_REPLIES.get(intent) or GREETING_REPLIES.get("ack_complete")
    return random.choice(pool) if pool else "好的。"


# ── Decay helper ────────────────────────────────────────────────

HINT_DECAY_HALF_LIFE: int = 3600  # 1 hour half-life for degradation penalty

def _get_confidence_decay(session: object | None) -> float:
    """Read historical degradation events, weighted by time decay.
    
    Prevents the system from becoming progressively more conservative
    after a single misclassification.
    """
    if session is None:
        return 1.0
    degradations = getattr(session, "degradation_history", [])
    if not degradations:
        return 1.0
    now = __import__("time").time()
    penalty = 0.0
    for ts, delta in degradations:
        age = now - ts
        penalty += delta * (0.5 ** (age / HINT_DECAY_HALF_LIFE))
    return max(1.0 - penalty, 0.5)  # floor 0.5 — never kill commerce entirely


# ════════════════════════════════════════════════════════════════════
# Main Entry Point
# ════════════════════════════════════════════════════════════════════

_INTENT_LABELS: dict[str, str] = {
    "greeting":    "问候语 — 模板回复",
    "chat":        "闲聊/辅助 — LLM直出",
    "commerce":    "商业意图 — 走全图",
    "unclear":     "意图不明确 — 降级到闲聊",
    "ack_resolve": "上下文补全 — 走全图",
    "search":      "搜索意图 — 走全图",
    "recommend":   "推荐意图 — 走全图",
    "clarify":     "澄清轮次 — 走全图",
}


def route(query: str, session: object | None = None) -> RouteDecision:
    """Thin orchestrator: Layer 1 → Layer 2 → Layer 3 → RouteDecision.

    Session interface expected:
      .pending_slots   (dict | None)   — unfilled slot keys
      .pending_question (str | None)   — question the AI asked the user
      .last_updated    (datetime|None) — for staleness check
      .active_domain   (str | None)    — e.g. "electronics"
    """
    # ── Safety: discard stale sessions ──
    if _is_session_stale(session):
        session = None

    # ── Layer 1: Intent Classification (pure text) ──
    result = _classify_intent(query)
    raw_intent: str = result["intent"]
    confidence: float = result["confidence"]
    candidates: list[str] = result["candidates"]
    if len(candidates) > 1:
        raw_intent = _resolve_conflict(candidates, session)

    # ── Layer 2: Context Resolution (slot filling) ──
    resolved_query: str | None = query
    control_context: dict = {}
    if _needs_resolve(query, session, raw_intent):
        resolved_query, control_context = _resolve(query, session)
        if control_context.get("resolved_slots"):
            raw_intent = "ack_resolve"

    # ── Gibberish fast path: template reply, zero LLM ──
    if raw_intent == "unclear" and confidence == 0.0:
        return RouteDecision(
            intent="unclear",
            confidence=0.0,
            reason="无效输入 — 模板回复",
            candidates=candidates,
            resolved_query=None,
            control_context={},
            execution_hint="trivial",
            needs_commerce_layer=False,
            needs_llm=False,
            needs_db=False,
        )

    # ── Layer 3: Policy Engine (execution + cost) ──
    execution_hint, needs_llm, needs_db, needs_commerce = _plan_execution(raw_intent, control_context)

    # ── Commerce domain gate ──
    # Commerce detected → ALWAYS enter commerce execution graph.
    # Never downgrade to chat — even low-confidence commerce queries
    # must search the database, not hallucinate via bare LLM.
    # execution_hint controls depth: full_graph for high confidence,
    # graph_light for low confidence — but BOTH go through search_node.
    if raw_intent == "commerce":
        from .commerce_intent import classify as classify_commerce, CONFIDENCE_CONFIG
        commerce_result = classify_commerce(query)
        confidence = commerce_result.confidence
        if confidence < CONFIDENCE_CONFIG["low_confidence"]:
            execution_hint = "full_graph"  # still graph, but entry_router handles fallback
        else:
            execution_hint = "full_graph"
        needs_llm = True
        needs_db = True
        needs_commerce = True

    # ── Build reason ──
    reason = _INTENT_LABELS.get(raw_intent,
                               f"未知意图「{raw_intent}」— 降级到闲聊")

    return RouteDecision(
        intent=raw_intent,
        confidence=confidence,
        reason=reason,
        candidates=candidates,
        resolved_query=resolved_query,
        control_context=control_context,
        execution_hint=execution_hint,
        needs_commerce_layer=needs_commerce,
        needs_llm=needs_llm,
        needs_db=needs_db,
    )
