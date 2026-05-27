"""
Preprocessor — deterministic state interpreter for multi-turn conversations.

Runs BEFORE Input Guard. Resolves short confirmations, slot selections,
and pronoun continuations without any LLM calls.

Output: ResolvedAction (not a text string) — directly controls execution flow.

Usage:
    from agents.graph.preprocessor import resolve

    conv_state = get_conversation_state(session_id)
    action = resolve(user_input, conv_state)
    # action.type ∈ {"direct_execute", "rewrite", "pass"}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ResolvedAction:
    """Deterministic routing decision. NOT a text rewrite."""
    type: Literal["direct_execute", "rewrite", "pass"]
    intent: str | None = None       # direct_execute: override intent
    query: str | None = None         # direct_execute/rewrite: effective query
    params: dict | None = None       # direct_execute: extra params (filters, slots)


@dataclass
class DialogueContext:
    """Per-session dialogue state — strictly separate from execution data."""
    injected_slot: str | None = None          # user's fill answer ("数码")
    last_user_query: str = ""                  # previous round's user query
    expects_followup: bool = False             # system left a gap → waiting


@dataclass
class ConversationState:
    """Snapshot of what the AI is waiting for, stored per session."""
    session_id: str
    last_intent: str = ""                       # "search" | "recommend" | "chat"
    pending_action_type: str = ""               # "confirm" | "clarify" | ""
    pending_question: str = ""                  # What the AI asked
    pending_options: dict[str, dict] = field(default_factory=dict)  # {opt_id: {label, intent?, params?}}
    original_query: str = ""                    # The query that triggered this clarify round
    context_summary: str = ""                   # One-line summary of last turn
    created_at: float = 0.0
    dialogue: DialogueContext = field(default_factory=DialogueContext)


# ═══════════════════════════════════════════════════════════════
# Recognizers
# ═══════════════════════════════════════════════════════════════

# Strict whitelist — words that unambiguously mean "yes" in Chinese/English
CONFIRM_WORDS: set[str] = {
    "对", "好", "嗯", "是的", "可以", "行", "没错", "对的",
    "yes", "ok", "okay", "yeah", "yep", "yup", "sure", "alright",
}

# Slot index patterns: "第2个", "第二个", "2", "二", "opt_2"
_SLOT_INDEX_RE = re.compile(r'(?:第\s*)?(\d+|一|二|三|四|五|六|七|八|九|十)\s*(?:个|项|种|条)?')
_CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# Pronoun/ack words — low-information inputs that likely continue previous context
PRONOUN_OR_ACK: set[str] = {
    "它", "他", "她", "这个", "那个", "哪个", "这些", "那些",
    "便宜一点的", "贵一点的", "更好", "有便宜的吗", "有没有更好的",
    "换一个", "再看看", "继续", "然后呢", "还有吗", "别的呢",
    "不要", "算了", "不用了", "不需要",
}


def _normalize(s: str) -> str:
    """Fullwidth→halfwidth, strip, lowercase."""
    result = []
    for ch in s:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            result.append(" ")
        else:
            result.append(ch)
    return "".join(result).strip().lower()


def is_confirm(input_str: str) -> bool:
    return _normalize(input_str) in CONFIRM_WORDS


def is_pronoun_or_ack(input_str: str) -> bool:
    return _normalize(input_str) in PRONOUN_OR_ACK


def parse_slot_index(input_str: str, num_options: int) -> int | None:
    """Parse "第2个", "2", "二" → 0-based index, or None."""
    norm = _normalize(input_str)
    m = _SLOT_INDEX_RE.search(norm)
    if not m:
        return None
    raw = m.group(1)
    if raw in _CN_DIGIT:
        n = _CN_DIGIT[raw]
    else:
        try:
            n = int(raw)
        except ValueError:
            return None
    if 1 <= n <= num_options:
        return n - 1
    return None


# ═══════════════════════════════════════════════════════════════
# Resolver
# ═══════════════════════════════════════════════════════════════

def resolve(user_input: str, state: ConversationState | None) -> ResolvedAction:
    """Deterministic state interpretation. Returns ResolvedAction, never a string.

    Three resolution paths:
      1. Slot resolution — "对", "第2个", "opt_1"
      2. Continuation binding — pronoun/low-info words
      3. Pass — let Input Guard + LLM handle it
    """
    if not state or not state.pending_action_type:
        return ResolvedAction(type="pass")

    norm = _normalize(user_input)

    # ── 1. Slot resolution ──────────────────────────────────

    # 1a. "对" / "yes" — only in "confirm" mode with exactly 1 option
    if state.pending_action_type == "confirm" and norm in CONFIRM_WORDS:
        options = list(state.pending_options.values())
        if len(options) == 1:
            opt = options[0]
            merged_query = _merge_query(state.original_query, opt["label"])
            return ResolvedAction(
                type="direct_execute",
                intent=opt.get("intent", state.last_intent),
                query=merged_query,
                params=_merge_params(opt.get("params"), state.original_query, opt["label"]),
            )

    # 1b. Slot index — "第2个", "2"
    if state.pending_action_type in ("confirm", "clarify"):
        idx = parse_slot_index(user_input, len(state.pending_options))
        if idx is not None:
            opt = list(state.pending_options.values())[idx]
            merged_query = _merge_query(state.original_query, opt["label"])
            return ResolvedAction(
                type="direct_execute",
                intent=opt.get("intent", state.last_intent),
                query=merged_query,
                params=_merge_params(opt.get("params"), state.original_query, opt["label"]),
            )

    # 1c. Exact option ID match — "opt_1", "opt_price_23_57"
    if norm in state.pending_options:
        opt = state.pending_options[norm]
        merged_query = _merge_query(state.original_query, opt["label"])
        return ResolvedAction(
            type="direct_execute",
            intent=opt.get("intent", state.last_intent),
            query=merged_query,
            params=_merge_params(opt.get("params"), state.original_query, opt["label"]),
        )

    # ── 2. Continuation binding ─────────────────────────────
    # Only trigger on pronoun/ack words, NOT on short content words
    if is_pronoun_or_ack(user_input) and state.last_intent:
        return ResolvedAction(
            type="rewrite",
            query=f"{state.context_summary}。用户追问: {user_input}",
        )

    # ── 3. Pass — unresolvable ─────────────────────────────
    return ResolvedAction(type="pass")


# ═══════════════════════════════════════════════════════════════
# Session State Builder
# ═══════════════════════════════════════════════════════════════

def build_conversation_state(
    session_id: str,
    last_intent: str,
    original_query: str,
    clarify_data: dict | None,
    ai_reply: str,
) -> ConversationState:
    """Build ConversationState after an AI response.

    If clarify_data is present → AI is waiting for user input → set pending state.
    Otherwise → clear pending state (conversation is resolved).
    """
    state = ConversationState(
        session_id=session_id,
        last_intent=last_intent,
        original_query=original_query,
        context_summary=f"用户询问「{original_query}」，AI 回复「{ai_reply[:80]}」",
    )

    if clarify_data:
        options_raw = clarify_data.get("options", [])
        state.pending_question = clarify_data.get("question", "")

        # Determine action type from the question semantics
        question = clarify_data.get("question", "").lower()
        if any(w in question for w in ("是否", "对吗", "确认", "是不是", "confirm", "right")):
            state.pending_action_type = "confirm"
        else:
            state.pending_action_type = "clarify"

        # Normalize options to {id: {label, intent?, params?}} dict
        state.pending_options = _normalize_options(options_raw, last_intent)

    return state


def _normalize_options(options: list, default_intent: str) -> dict[str, dict]:
    """Convert options from simple strings or structured dicts into a uniform dict.

    Input:  ["23-57", "57-100"]  or  [{"id":"opt_1","label":"..."}]
    Output: {"opt_1": {"label":"23-57", "intent":"search"}, ...}
    """
    result: dict[str, dict] = {}
    for i, opt in enumerate(options):
        if isinstance(opt, dict):
            opt_id = opt.get("id", f"opt_{i+1}")
            result[opt_id] = {
                "label": opt.get("label", str(opt)),
                "intent": opt.get("intent", default_intent),
                "params": opt.get("params"),
            }
        else:
            # Simple string → auto-generate ID
            opt_label = str(opt)
            result[f"opt_{i+1}"] = {
                "label": opt_label,
                "intent": default_intent,
                "params": None,
            }
    return result


def _merge_query(original: str, slot_label: str) -> str:
    """Merge original query context with the resolved slot label.

    e.g. original="推荐蓝牙耳机", slot_label="0 - 6"
         → "推荐蓝牙耳机 预算0-6"
    """
    if not original:
        return slot_label
    if not slot_label:
        return original
    # Avoid duplicating if slot_label is already part of original
    if slot_label in original:
        return original
    return f"{original} {slot_label}"


def _merge_params(opt_params: dict | None, original: str, slot_label: str) -> dict:
    """Merge option params with original query context."""
    result = dict(opt_params) if opt_params else {}
    result["_original_query"] = original
    result["_slot_value"] = slot_label
    return result
