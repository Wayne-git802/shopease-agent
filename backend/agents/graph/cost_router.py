"""
CostRouter — per-node model selection strategy.

Selects cheap vs premium models based on estimated token counts.
Deterministic nodes (order, ops) always use cheap.
Other nodes compare estimated_tokens against per-node thresholds.

Also provides estimate_tokens(state) helper for token estimation.
"""

import logging
from typing import Optional

from .state import AgentState

logger = logging.getLogger(__name__)

# ── Node Strategies ────────────────────────────────────────────────

# Each entry defines:
#   threshold: max tokens before switching to premium model
#   cheap:     model name when estimated_tokens <= threshold (or node is deterministic)
#   premium:   model name when estimated_tokens > threshold

NODE_STRATEGY: dict[str, dict[str, object]] = {
    "search":    {"threshold": 500,  "cheap": "deepseek-v4-pro", "premium": "deepseek-v4-pro"},
    "recommend": {"threshold": 2000, "cheap": "deepseek-v4-pro", "premium": "deepseek-v4-pro"},
    "order":     {"threshold": 100,  "cheap": "deepseek-v4-pro", "premium": "deepseek-v4-pro"},
    "ops":       {"threshold": 100,  "cheap": "deepseek-v4-pro", "premium": "deepseek-v4-pro"},
    "chat":      {"threshold": 800,  "cheap": "deepseek-v4-pro", "premium": "deepseek-v4-pro"},
    "response":  {"threshold": 1500, "cheap": "deepseek-v4-pro", "premium": "deepseek-v4-pro"},
}

# Nodes that are deterministic (no LLM call needed, always use cheap)
DETERMINISTIC_NODES: set[str] = {"order", "ops"}

# Rough character-to-token ratio (~4 chars per token for English, ~2 for Chinese)
TOKENS_PER_CHAR = 0.25


# ── CostRouter ─────────────────────────────────────────────────────

class CostRouter:
    """Selects the appropriate model for each node based on estimated cost.

    Decision rules:
      - Deterministic nodes (order, ops) → always cheap.
      - Other nodes: compare estimated_tokens against node threshold.
        - tokens <= threshold → cheap
        - tokens >  threshold → premium
    """

    def __init__(self, strategy: dict[str, dict[str, object]] | None = None) -> None:
        self.strategy = strategy or NODE_STRATEGY

    def select(self, node_name: str, estimated_tokens: int) -> str:
        """Select model name for a given node and token estimate.

        Args:
            node_name: The node being executed (e.g., "search", "chat", "response").
            estimated_tokens: Estimated number of tokens for this invocation.

        Returns:
            Model name string (e.g., "deepseek-v4-pro").
        """
        node_strategy = self.strategy.get(node_name)
        if node_strategy is None:
            logger.warning(
                "No strategy for node '%s', using cheap default", node_name,
            )
            return "deepseek-v4-pro"

        cheap_model = str(node_strategy["cheap"])
        premium_model = str(node_strategy["premium"])
        threshold = int(node_strategy["threshold"])

        # Deterministic nodes always use cheap
        if node_name in DETERMINISTIC_NODES:
            logger.debug(
                "CostRouter: node='%s' is deterministic → cheap (%s)",
                node_name, cheap_model,
            )
            return cheap_model

        # Token-based threshold selection
        if estimated_tokens <= threshold:
            logger.debug(
                "CostRouter: node='%s', tokens=%d <= %d → cheap (%s)",
                node_name, estimated_tokens, threshold, cheap_model,
            )
            return cheap_model
        else:
            logger.debug(
                "CostRouter: node='%s', tokens=%d > %d → premium (%s)",
                node_name, estimated_tokens, threshold, premium_model,
            )
            return premium_model

    def get_threshold(self, node_name: str) -> int | None:
        """Get the token threshold for a node, if configured."""
        node_strategy = self.strategy.get(node_name)
        if node_strategy is None:
            return None
        return int(node_strategy["threshold"])


# ── Token Estimation ───────────────────────────────────────────────

def estimate_tokens(state: AgentState) -> int:
    """Estimate token count from the current AgentState.

    Uses character-based heuristics (~4 chars per token for English).
    Accounts for query, history, retrieved products/docs, tool results,
    and final response.

    Args:
        state: Current AgentState (SSOT).

    Returns:
        Estimated token count (int, minimum 1).
    """
    total_chars = 0

    # User query
    total_chars += len(state.user_query)

    # Conversation history
    for msg in state.history:
        content = msg.content if hasattr(msg, "content") else str(msg)
        total_chars += len(content)

    # Retrieved products (name + category)
    for product in state.retrieved_products:
        name = product.name if hasattr(product, "name") else str(product)
        category = product.category if hasattr(product, "category") else ""
        total_chars += len(name) + len(category)

    # Retrieved docs
    for doc in state.retrieved_docs:
        content = doc.content if hasattr(doc, "content") else str(doc)
        total_chars += len(content)

    # Final response (if generating)
    total_chars += len(state.final_response)

    # Tool results (keys + values as strings)
    for key, value in state.tool_results.items():
        total_chars += len(str(key)) + len(str(value))

    # User memory (if loaded)
    if state.user_memory is not None:
        preferences_str = str(state.user_memory.preferences)
        total_chars += len(preferences_str)

    estimated = max(1, int(total_chars * TOKENS_PER_CHAR))
    logger.debug("estimate_tokens: %d chars → ~%d tokens", total_chars, estimated)
    return estimated
