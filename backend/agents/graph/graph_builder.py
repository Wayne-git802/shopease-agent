"""
Graph Builder — compiled LangGraph StateGraph singleton.

Nodes:
  START → entry_router → [conditional edge based on intent]
                            ├─"search"    → search   → response → END
                            ├─"recommend" → search   → response → END
                            ├─"order"     → order    → chat → response → END
                            ├─"analytics" → analytics → response → END
                            └─"chat"      → chat     → response → END

Phase 6 merge: recommend_node and merge_node removed — search_node handles
all retrieval (EXACT/SOFT/EXPLORE modes) with unified ranking.
"""

from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes.entry_router import entry_router
from .nodes.chat_node import chat_node
from .nodes.response_node import response_node
from .nodes.search_node import search_node
from .nodes.order_node import order_node
from .nodes.analytics_node import analytics_node


def build_graph() -> StateGraph:
    """Build and compile the main LangGraph StateGraph."""
    graph = StateGraph(AgentState)

    graph.add_node("entry_router", entry_router)
    graph.add_node("search", search_node)
    graph.add_node("chat", chat_node)
    graph.add_node("response", response_node)
    graph.add_node("order", order_node)
    graph.add_node("analytics", analytics_node)

    graph.set_entry_point("entry_router")

    graph.add_conditional_edges(
        "entry_router",
        lambda state: state.intent,
        {
            "search": "search",
            "recommend": "search",    # phase 6: merged into search_node (SOFT mode)
            "order": "order",
            "analytics": "analytics",
            "chat": "chat",
        },
    )

    graph.add_edge("search", "response")
    graph.add_edge("chat", "response")
    graph.add_edge("response", END)
    graph.add_edge("order", "chat")
    graph.add_edge("analytics", "response")

    return graph.compile()


_compiled_graph = build_graph()


def get_graph():
    """Return the compiled graph singleton."""
    return _compiled_graph
