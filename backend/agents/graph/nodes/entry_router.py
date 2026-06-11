"""
entry_router node — LangGraph dispatcher + execution-context reference resolution.

Dispatch priority:
  0. Reference resolution — resolve "第一个"/"第二个" BEFORE dispatch
  1. Preset intent from state_router
  2. ConstraintParser override (search_plan intent)
  3. Session memory (follow-up answer to clarify question)
  4. Default → "chat"

Phase 6 fix: reference resolution runs FIRST, before any dispatch path.
If resolved, preset_intent is set to the last known intent so downstream
nodes receive the right routing context.
"""

import logging

from langgraph.types import Command

from ..state import AgentState

logger = logging.getLogger(__name__)

_CONSTRAINT_NODE_MAP: dict[str, str] = {"sort": "search", "recommend": "recommend"}
VALID_INTENTS = {"search", "recommend", "order", "analytics", "chat"}


def entry_router(state: AgentState) -> Command:
    """Dispatch to the correct graph node.  Reference resolution runs first."""

    query = state.user_query or ""
    session_id = state.session_id or ""

    # ═══════════════════════════════════════════════════════════
    # Path 0: Reference resolution (BEFORE all dispatch paths)
    # ═══════════════════════════════════════════════════════════
    _try_resolve_reference(state, query, session_id)

    # Base update — always include parallel_results so LangGraph
    # preserves in-place mutations made by _try_resolve_reference.
    base_update = {
        "current_node": "entry_router",
        "parallel_results": state.parallel_results,
    }

    # ── Path 1: Preset intent ──
    preset = state.control_context.get("preset_intent", "")
    if preset in VALID_INTENTS:
        return Command(goto=preset, update={
            **base_update,
            "intent": preset, "confidence": 0.9,
            "routing_method": "preset",
            "ui_message": f"匹配到「{preset}」意图（路由预设）",
        })

    # ── Path 2: ConstraintParser ──
    search_plan = state.parallel_results.get("_search_plan")
    if search_plan:
        intent = search_plan.get("intent", "chat")
        if intent != "ambiguous":
            goto = _CONSTRAINT_NODE_MAP.get(intent, intent)
            if goto not in VALID_INTENTS:
                goto = "chat"
            return Command(goto=goto, update={
                **base_update,
                "intent": goto, "confidence": 0.95,
                "routing_method": "constraint_parser",
                "ui_message": f"匹配到「{intent}」意图（约束解析）",
            })

    # ── Path 3: Session memory ──
    from agents.graph.session_memory import get as get_session_memory, collect_answer
    session_mem = get_session_memory(session_id)
    if session_mem and session_mem.pending_intent:
        if session_mem.missing_slots:
            for slot_key in session_mem.missing_slots:
                collect_answer(session_id, slot_key, query)
        return Command(goto=session_mem.pending_intent, update={
            **base_update,
            "intent": session_mem.pending_intent, "confidence": 1.0,
            "routing_method": "session", "clarify_round": 1,
            "ui_message": f"继续「{session_mem.pending_intent}」流程…",
        })

    # ── Path 4: Default ──
    logger.info("No preset_intent — defaulting to chat")
    return Command(goto="chat", update={
        **base_update,
        "intent": "chat", "confidence": 0.5,
        "routing_method": "default",
        "ui_message": "你好！有什么可以帮你的？",
    })


# ═══════════════════════════════════════════════════════════════
# Reference resolution (Path 0)
# ═══════════════════════════════════════════════════════════════

def _try_resolve_reference(state: AgentState, query: str, session_id: str) -> None:
    """Resolve product references BEFORE dispatch.  Sets _resolved_product_id
    and preset_intent on state so dispatch paths route correctly."""
    if not session_id or not query.strip():
        return
    if not _has_reference(query):
        return

    import django
    django.setup()
    from agents.models import AgentConversation
    from agents.graph.session_memory import get_conv_state

    # 1. Look up displayed products from last assistant message
    msg = (
        AgentConversation.objects
        .filter(session_id=session_id, role="assistant")
        .order_by("-created_at")
        .first()
    )
    if not msg or not msg.metadata:
        return

    products = []
    for b in msg.metadata.get("blocks", []):
        if b.get("type") == "product_card":
            products = b.get("data", {}).get("products", [])
            break
    if not products:
        return

    # 2. Resolve index
    import re
    m = re.search(r'第\s*([\d一二两三四五六七八九十]+)\s*[个款]', query)
    if not m:
        return

    num_str = m.group(1)
    NUM_MAP = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    idx = NUM_MAP.get(num_str, int(num_str) if num_str.isdigit() else 1) - 1
    if idx < 0 or idx >= len(products):
        logger.debug("Reference index %d out of range (products=%d)", idx, len(products))
        return

    p = products[idx]
    state.parallel_results["_resolved_product_id"] = p.get("product_id", p.get("id", 0))
    state.parallel_results["_resolved_product_name"] = p.get("name", p.get("product_name", ""))

    # 3. Recover last intent so dispatch knows where to go
    cs = get_conv_state(session_id)
    last_intent = cs.last_intent if cs else "search"
    if last_intent not in VALID_INTENTS:
        last_intent = "search"
    state.control_context["preset_intent"] = last_intent

    logger.debug("Resolved reference '%s' → id=%s name=%s intent=%s",
                 query, state.parallel_results["_resolved_product_id"],
                 state.parallel_results["_resolved_product_name"], last_intent)


def _has_reference(query: str) -> bool:
    """True if query contains an index-based product reference."""
    import re
    return bool(re.search(r'第\s*[一二两三四五六七八九十\d]+\s*[个款]', query))
