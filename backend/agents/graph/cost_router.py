"""
Per-node model selection + token estimation.

Currently all nodes use the same model.  The CostRouter class and per-node
strategy table are removed in favour of a single constant.  When multi-model
routing is needed, re-introduce a strategy table keyed by node name.
"""
from __future__ import annotations

from .state import AgentState

# Single model for all nodes (was: per-node cheap/premium, both identical).
DEFAULT_MODEL = "deepseek-v4-pro"

# Rough character-to-token ratio (~4 chars per token for English, ~2 for Chinese)
TOKENS_PER_CHAR = 0.25


def estimate_tokens(state: AgentState) -> int:
    """Estimate token count from current AgentState (character heuristic).

    Accounts for query, history, retrieved products/docs, tool results,
    final response, and user memory.
    """
    total_chars = len(state.user_query)

    for msg in state.history:
        content = msg.content if hasattr(msg, "content") else str(msg)
        total_chars += len(content)

    for product in state.retrieved_products:
        name = product.name if hasattr(product, "name") else str(product)
        category = product.category if hasattr(product, "category") else ""
        total_chars += len(name) + len(category)

    for doc in state.retrieved_docs:
        content = doc.content if hasattr(doc, "content") else str(doc)
        total_chars += len(content)

    total_chars += len(state.final_response)

    for key, value in state.tool_results.items():
        total_chars += len(str(key)) + len(str(value))

    if state.user_memory is not None:
        total_chars += len(str(state.user_memory.preferences))

    return max(1, int(total_chars * TOKENS_PER_CHAR))
