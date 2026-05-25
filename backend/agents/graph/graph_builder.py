"""
Graph Builder — compiled LangGraph StateGraph singleton.

Nodes:
  START → entry_router → [conditional edge based on intent]
                            ├─"search"    → search    → merge → response → END
                            ├─"recommend" → recommend → merge → response → END
                            ├─"order"     → order     → chat  → response → END
                            ├─"ops"       → ops       → chat  → response → END
                            ├─"analytics" → analytics → response → END
                            └─"chat"      → chat      → response → END

entry_router classifies intent and returns Command(goto=intent, update={...}),
while add_conditional_edges provides the routing map for state-based dispatch.

The graph compiles once at import time.
"""
from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes.entry_router import entry_router
from .nodes.chat_node import chat_node
from .nodes.response_node import response_node
from .nodes.merge_node import merge_node
from .nodes.search_node import search_node
from .nodes.recommend_node import recommend_node
from .nodes.order_node import order_node
from .nodes.ops_node import ops_node
from .nodes.analytics_node import analytics_node


def build_graph() -> StateGraph:
    """Build and compile the main LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    # ── Add all nodes ──
    graph.add_node("entry_router", entry_router)
    graph.add_node("chat", chat_node)
    graph.add_node("response", response_node)
    graph.add_node("merge", merge_node)
    graph.add_node("search", search_node)
    graph.add_node("recommend", recommend_node)
    graph.add_node("order", order_node)
    graph.add_node("ops", ops_node)
    graph.add_node("analytics", analytics_node)

    # ── Entry point ──
    graph.set_entry_point("entry_router")

    # ── Conditional routing from entry_router ──
    graph.add_conditional_edges(
        "entry_router",
        lambda state: state.intent,
        {
            "search": "search",
            "recommend": "recommend",
            "order": "order",
            "ops": "ops",
            "analytics": "analytics",
            "chat": "chat",
        },
    )

    # ── Chat → response → END ──
    graph.add_edge("chat", "response")
    graph.add_edge("response", END)

    # ── Parallel fan nodes → merge → response ──
    graph.add_edge("search", "merge")
    graph.add_edge("recommend", "merge")
    graph.add_edge("merge", "response")

    # ── Simple passthrough nodes → chat → response ──
    graph.add_edge("order", "chat")
    graph.add_edge("ops", "chat")

    # ── Analytics → response ──
    graph.add_edge("analytics", "response")

    return graph.compile()


# ── Compiled singleton ──
_compiled_graph = build_graph()


def get_graph():
    """Return the compiled graph singleton."""
    return _compiled_graph
