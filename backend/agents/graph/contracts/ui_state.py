"""
UI State Protocol — the contract between LangGraph and the frontend.

The frontend consumes ONLY cognitive UI states (understanding, searching,
recommending...) and NEVER knows about graph internals (node names, routing
logic, implementation details).

If we rename a node, split a node, or add a node — the frontend sees zero
changes as long as the cognitive mapping stays consistent.
"""

from enum import StrEnum
from pydantic import BaseModel, Field


# ── Cognitive UI States ──────────────────────────────────────────────

class UIState(StrEnum):
    """Cognitive states visible to the user — NOT graph implementation."""
    UNDERSTANDING = "understanding"    # 正在理解你的需求…
    SEARCHING     = "searching"        # 正在搜索相关商品…
    RECOMMENDING  = "recommending"     # 正在分析偏好，为你排序…
    ANALYZING     = "analyzing"        # 正在生成分析报告…
    CHATTING      = "chatting"         # 对话中
    ORDERING      = "ordering"         # 处理订单…
    CHECKING      = "checking"         # 检查系统状态…
    DONE          = "done"             # ✓ 完成
    FALLBACK      = "fallback"         # 降级到对话模式
    ERROR         = "error"            # 处理出错
    CLARIFYING    = "clarifying"       # 🆕 P3: asking a follow-up question


# ── Default human-readable messages ───────────────────────────────────

UI_STATE_MESSAGES: dict[UIState, str] = {
    UIState.UNDERSTANDING: "正在理解你的需求…",
    UIState.SEARCHING:     "正在搜索相关商品…",
    UIState.RECOMMENDING:  "正在分析你的偏好，为你排序…",
    UIState.ANALYZING:     "正在生成分析报告…",
    UIState.CHATTING:      "",
    UIState.ORDERING:      "正在处理订单…",
    UIState.CHECKING:      "正在检查系统状态…",
    UIState.DONE:          "",
    UIState.FALLBACK:      "切换到对话模式…",
    UIState.ERROR:         "处理出错了",
    UIState.CLARIFYING:    "需要确认一些信息…",
}


# ── Node-to-UI-State Mapping ─────────────────────────────────────────
# This is the ONLY place where graph internals are mapped to UI surface.
# If you rename/split/add a node, update this dict — frontend unchanged.

NODE_TO_UI_STATE: dict[str, UIState] = {
    "entry_router": UIState.UNDERSTANDING,
    "search":       UIState.SEARCHING,
    "recommend":    UIState.RECOMMENDING,
    "order":        UIState.ORDERING,
    "ops":          UIState.CHECKING,
    "analytics":    UIState.ANALYZING,
    "chat":         UIState.CHATTING,
    "merge":        UIState.RECOMMENDING,
    "response":     UIState.DONE,
}


# ── Response contract ─────────────────────────────────────────────────

class UIBlock(BaseModel):
    """A renderable block in the AI response."""
    type: str  # "product_card" | "text" | "metric" | "report" | "alert" | "clarify" | "explain"
    data: dict = Field(default_factory=dict)


class AIResponse(BaseModel):
    """The unified response format that the frontend consumes.

    This is the ONLY contract. The frontend never sees state dicts,
    node names, or graph internals.
    """
    ui_state:   UIState               # cognitive state
    message:    str = ""              # human-readable status
    confidence: float = 0.0           # routing confidence [0, 1]
    blocks:     list[UIBlock] = Field(default_factory=list)  # renderable blocks
    reply:      str = ""              # plain-text reply (chat / analytics)
    intent:     str = ""              # raw intent (for debug / transition)
    trace:      dict | None = None    # optional debug summary
    # Phase 0: UI hints from ConstraintParser
    show_budget_hint: bool = False     # render lightweight budget picker
    show_clarify_hint: bool = False    # render "tell me more" prompt
