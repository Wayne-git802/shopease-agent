"""
Query Grounding Layer — determines whether a commerce query is executable.

Architecture:
  Grounder (pure lexical) → slots dict
  Planner (decision)      → QueryGroundingResult

This is NOT a slot validator.  It answers one question:
  "Can this query be mapped to a finite, searchable product space?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .lexicon import CATEGORY_LEXICON as ProductLexicon

# ═══════════════════════════════════════════════════════════════
# Constants
HIGH_INTENT_GOALS: set[str] = {
    "礼物", "送人", "送礼", "好东西", "值得买",
    "送女友", "送男朋友", "送爸妈", "送朋友", "送孩子",
    "gift", "present",
}

MAX_CLARIFY_DEPTH = 2

# ═══════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════

class SearchState(str, Enum):
    READY              = "ready"               # go straight to search
    NEEDS_REFINEMENT   = "needs_refinement"    # searchable but broad
    NEEDS_CATEGORY     = "needs_category"      # must clarify


@dataclass
class QueryGroundingResult:
    state: SearchState
    product_anchor: str | None = None
    abstract_goal: str | None = None
    descriptor: str | None = None
    budget: tuple[float, float] | None = None
    recipient: str | None = None
    occasion: str | None = None
    usage: str | None = None
    missing_slot: str | None = None
    confidence: float = 0.0
    all_slots: dict[str, Any] = field(default_factory=dict)


@dataclass
class GroundingMemory:
    """Accumulated constraints across clarify rounds — NOT a query string merge."""
    constraints: dict[str, Any] = field(default_factory=dict)
    current_goal: str = ""
    depth: int = 0


CLARIFY_TEMPLATES: dict[str, str] = {
    "category":  "想要什么类型的商品呢？比如耳机、键盘、香水...",
    "budget":    "预算大概多少？",
    "recipient": "是送给谁的？",
    "occasion":  "是什么场合呢？",
    "usage":     "主要用来做什么？",
}

# ═══════════════════════════════════════════════════════════════
# Grounder — pure lexical extraction
# ═══════════════════════════════════════════════════════════════

def ground(query: str) -> dict[str, Any]:
    """Extract structured slots from query text.  Zero LLM, pure lexical."""
    import re

    slots: dict[str, Any] = {
        "category":       None,
        "abstract_goal":  None,
        "descriptor":     None,
        "budget":         None,
        "recipient":      None,
        "occasion":       None,
        "usage":          None,
    }

    q = query.lower()
    matched: dict[str, str] = {}  # token → label

    # Longest-match scan through lexicon
    for token, label in sorted(ProductLexicon.items(), key=lambda x: -len(x[0])):
        if token in query or token.lower() in q:
            if token not in matched:
                matched[token] = label

    # Assign to slot by label
    for token, label in matched.items():
        if label == "category":
            slots["category"] = token
        elif label == "abstract_goal" and slots["abstract_goal"] is None:
            slots["abstract_goal"] = token
        elif label == "descriptor" and slots["descriptor"] is None:
            slots["descriptor"] = token

    # Budget extraction
    m = re.search(r"(\d+)\s*(?:以内|以下|之内)", query)
    if m:
        slots["budget"] = (0, int(m.group(1)))
    else:
        m = re.search(r"(\d+)\s*[-–]\s*(\d+)", query)
        if m:
            slots["budget"] = (int(m.group(1)), int(m.group(2)))
        else:
            m = re.search(r"(\d+)元?", query)
            if m:
                slots["budget"] = (0, int(m.group(1)))

    # Recipient
    for cn in ("女朋友", "男朋友", "妈妈", "爸爸", "爸妈", "朋友",
               "学生", "小孩", "孩子", "女友", "男友", "老婆", "老公"):
        if cn in query:
            slots["recipient"] = cn
            break

    # Occasion
    for cn in ("生日", "节日", "圣诞", "新年", "毕业", "结婚", "纪念日", "情人节"):
        if cn in query:
            slots["occasion"] = cn
            break

    # Usage
    for cn in ("学习", "工作", "游戏", "运动", "旅行", "通勤", "办公", "上课",
               "打游戏", "健身", "跑步", "看书"):
        if cn in query:
            slots["usage"] = cn
            break

    return slots


# ═══════════════════════════════════════════════════════════════
# Planner — executability decision
# ═══════════════════════════════════════════════════════════════

def plan(slots: dict[str, Any], depth: int = 0) -> QueryGroundingResult:
    """Decide search readiness from extracted slots."""

    result = QueryGroundingResult(
        state=SearchState.READY,
        product_anchor=slots.get("category"),
        abstract_goal=slots.get("abstract_goal"),
        descriptor=slots.get("descriptor"),
        budget=slots.get("budget"),
        recipient=slots.get("recipient"),
        occasion=slots.get("occasion"),
        usage=slots.get("usage"),
        all_slots=slots,
    )

    # Case 1: concrete category → always ready
    if slots["category"]:
        result.state = SearchState.READY
        result.confidence = 0.9
        return result

    # Case 2: high-intent abstract goal → NEEDS_REFINEMENT if has any support,
    # NEEDS_CATEGORY if standalone (no recipient/budget/usage/occasion).
    if slots["abstract_goal"] and slots["abstract_goal"] in HIGH_INTENT_GOALS:
        has_support = any([
            slots["recipient"], slots["budget"], slots["usage"], slots["occasion"],
        ])
        if has_support:
            result.state = SearchState.NEEDS_REFINEMENT
            result.missing_slot = "category"  # optional, not blocking
            result.confidence = 0.5
        elif depth >= MAX_CLARIFY_DEPTH:
            result.state = SearchState.NEEDS_REFINEMENT
            result.confidence = 0.3
        else:
            result.state = SearchState.NEEDS_CATEGORY
            result.missing_slot = "category"
            result.confidence = 0.2
        return result

    # Case 3: descriptor only → no anchor at all
    if slots["descriptor"] and not slots["category"] and not slots["abstract_goal"]:
        if depth >= MAX_CLARIFY_DEPTH:
            result.state = SearchState.NEEDS_REFINEMENT
            result.missing_slot = None
            result.confidence = 0.2
        else:
            result.state = SearchState.NEEDS_CATEGORY
            result.missing_slot = "category"
            result.confidence = 0.1
        return result

    # Case 4: has recipient/occasion but no category → needs refinement
    if slots["recipient"] or slots["occasion"]:
        if depth >= MAX_CLARIFY_DEPTH:
            result.state = SearchState.NEEDS_REFINEMENT
            result.confidence = 0.4
        else:
            result.state = SearchState.NEEDS_CATEGORY
            result.missing_slot = "category"
            result.confidence = 0.2
        return result

    # Case 5: nothing actionable → needs category
    if depth >= MAX_CLARIFY_DEPTH:
        result.state = SearchState.NEEDS_REFINEMENT
        result.confidence = 0.3
    else:
        result.state = SearchState.NEEDS_CATEGORY
        result.missing_slot = "category"
        result.confidence = 0.1

    return result


# ═══════════════════════════════════════════════════════════════
# Clarify helper
# ═══════════════════════════════════════════════════════════════

def build_clarify_reply(missing_slot: str) -> dict:
    """Build a clarify response block for the orchestrator."""
    question = CLARIFY_TEMPLATES.get(
        missing_slot,
        "能再说得具体一点吗？"
    )
    return {
        "reply": question,
        "intent": "clarify",
        "agent_type": "grounder",
        "blocks": [{
            "type": "clarify",
            "data": {
                "question": question,
                "missing_slot": missing_slot,
                "options": [],
            },
        }],
        "ui_state": "clarifying",
        "_pending_slot": missing_slot,
    }
