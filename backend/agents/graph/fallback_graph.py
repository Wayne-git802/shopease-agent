"""
Fallback Graph — degraded mode: direct chat, no RAG, no recommendations.

Used when the main graph fails irrecoverably.
"""
from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes.chat_node import chat_node
from .nodes.response_node import response_node


def build_fallback_graph() -> StateGraph:
    """Minimal graph: chat → response → END."""
    graph = StateGraph(AgentState)
    graph.add_node("chat", chat_node)
    graph.add_node("response", response_node)
    graph.set_entry_point("chat")
    graph.add_edge("chat", "response")
    graph.add_edge("response", END)
    return graph.compile()


_fallback_graph = build_fallback_graph()


def get_fallback_graph():
    return _fallback_graph
