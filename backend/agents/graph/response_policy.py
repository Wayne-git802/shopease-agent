# Response Policy — resource scheduler. Decides execution_mode, memory
# loading level, and LLM parameters. Does NOT call LLM, query DB, or
# control graph internals.  Pure rules, no LLM, no DB.

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMPolicy:
    max_tokens: int
    temperature: float = 0.7
    mode: str = "chat"          # "chat" | "graph_proxy"
    # "chat"         → single LLM call via chat_node, no tools
    # "graph_proxy"  → full graph execution, tools controlled by graph internally


@dataclass
class ExecutionPlan:
    execution_mode: str         # "template" | "llm_direct" | "graph_light" | "graph_full"
    memory: str                 # "none" | "preferences" | "purchase" | "full"
    llm: LLMPolicy


# BOUNDARY: llm.mode='graph_proxy' means the graph controls tools
# internally. Response Policy does not decide which tools — only which
# execution system to invoke.


# ── Decision table (pure rules) ────────────────────────────────────
#
# condition                         | exec_mode     | memory       | llm_mode     | max_tokens
# ──────────────────────────────────┼───────────────┼──────────────┼──────────────┼───────────
# intent=greeting, any confidence   | template      | none         | chat         | 0
# intent=chat, any confidence       | llm_direct    | none         | chat         | 200
# intent=commerce, confidence<0.3   | graph_light   | preferences  | graph_proxy  | 500
# intent=commerce, confidence 0.3+  | graph_full    | full         | graph_proxy  | 2000
# intent=search/recommend/explore   | graph_full    | full         | graph_proxy  | 2000
# intent=order, confidence>0.3      | graph_light   | purchase     | graph_proxy  | 500
# intent=analytics, any confidence  | graph_full    | none         | graph_proxy  | 2000
# fallback (unknown)                | graph_light   | none         | graph_proxy  | 500


def _build_plan(exec_mode: str, memory: str, llm_mode: str, max_tokens: int) -> ExecutionPlan:
    """Build an ExecutionPlan from row values, setting temperature by mode."""
    temp = 0.7 if llm_mode == "chat" else 0.3
    return ExecutionPlan(
        execution_mode=exec_mode,
        memory=memory,
        llm=LLMPolicy(max_tokens=max_tokens, temperature=temp, mode=llm_mode),
    )


def plan(route, commerce_result=None) -> ExecutionPlan:
    """Decide execution plan from route decision and optional commerce sub-intent.

    Args:
        route: RouteDecision from state_router (.intent, .confidence, ...)
        commerce_result: IntentResult from commerce_intent or None (.intent, .confidence)
    """
    intent = getattr(route, "intent", "chat")

    # ── Route-level intents ─────────────────────────────────
    if intent == "greeting":
        return _build_plan("template", "none", "chat", 0)

    if intent == "chat":
        return _build_plan("llm_direct", "none", "chat", 200)

    # ── Commerce: drill into sub-intent ─────────────────────
    if intent in ("commerce", "ack_resolve") and commerce_result is not None:
        sub = getattr(commerce_result, "intent", "search")
        conf = getattr(commerce_result, "confidence", 0.0)

        if sub == "analytics":
            return _build_plan("graph_full", "none", "graph_proxy", 2000)

        if sub == "order" and conf > 0.3:
            return _build_plan("graph_light", "purchase", "graph_proxy", 500)

        if sub in ("search", "recommend", "explore") and conf > 0.3:
            return _build_plan("graph_full", "full", "graph_proxy", 2000)

        # Commerce confidence gate — low confidence still goes through graph,
        # never bare LLM (no tool access → hallucination risk)
        if conf < 0.3:
            return _build_plan("graph_light", "preferences", "graph_proxy", 500)

        return _build_plan("graph_light", "preferences", "graph_proxy", 500)

    # ── Unclear / gibberish ────────────────────────────────
    if intent == "unclear":
        conf = getattr(route, "confidence", 0.5)
        if conf < 0.1:
            return _build_plan("template", "none", "chat", 0)
        return _build_plan("llm_direct", "none", "chat", 200)

    # ── Fallback: unknown ───────────────────────────────────
    return _build_plan("graph_light", "none", "graph_proxy", 500)
