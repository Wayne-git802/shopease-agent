"""
GraphPolicy — determines the next node in the LangGraph execution.

Rules:
  - TRANSPARENT passthrough: next_node = intent
    (e.g., intent="search" → node="search", intent="recommend" → node="recommend")
  - Fallback to "chat" when:
    1. confidence < 0.6
    2. intent == "recommend" AND retrieved_products is empty
    3. retry_exhausted: any node retried >= RETRY_MAX times OR steps >= MAX_STEPS
  - ENFORCE: Policy NEVER routes intent=A to next_node=B unless fallback to "chat".
"""

import logging
from collections import Counter
from typing import Optional

from .state import AgentState

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

MAX_STEPS = 8
RETRY_MAX = 2
FALLBACK_NODE = "chat"
CONFIDENCE_FALLBACK_THRESHOLD = 0.6

# Valid intents → node name mapping (identity mapping)
INTENT_NODE_MAP: dict[str, str] = {
    "search":    "search",
    "recommend": "recommend",
    "order":     "order",
    "ops":       "ops",
    "chat":      "chat",
}


# ── GraphPolicy ────────────────────────────────────────────────────

class GraphPolicy:
    """Determines the next node based on state and policy rules.

    Core principle: TRANSPARENT passthrough — next_node = intent.
    Only deviates from this rule when explicit fallback conditions are met,
    in which case fallback always goes to "chat".
    """

    def __init__(
        self,
        max_steps: int = MAX_STEPS,
        retry_max: int = RETRY_MAX,
        confidence_threshold: float = CONFIDENCE_FALLBACK_THRESHOLD,
    ) -> None:
        self.max_steps = max_steps
        self.retry_max = retry_max
        self.confidence_threshold = confidence_threshold

    def route(self, state: AgentState) -> str:
        """Determine the next node from the current state.

        Args:
            state: The full AgentState (SSOT).

        Returns:
            The name of the next node to execute.

        Fallback order:
            1. Low confidence → "chat"
            2. Recommend without products → "chat"
            3. Retry exhausted → "chat"
            4. Max steps reached → "chat"
            5. Unknown intent → "chat"
            6. Otherwise → transparent passthrough (next_node = intent)
        """
        intent = state.intent
        confidence = state.confidence
        steps_done = state.steps_done
        retrieved_products = state.retrieved_products

        # ── Fallback 1: Low confidence ────────────────────────
        if confidence < self.confidence_threshold:
            logger.warning(
                "Policy fallback: confidence=%.2f < %.2f → '%s'",
                confidence, self.confidence_threshold, FALLBACK_NODE,
            )
            return FALLBACK_NODE

        # ── Fallback 2: Recommend with no products ────────────
        if intent == "recommend" and not retrieved_products:
            logger.warning(
                "Policy fallback: intent='recommend' but retrieved_products is empty → '%s'",
                FALLBACK_NODE,
            )
            return FALLBACK_NODE

        # ── Fallback 3: Retry exhausted ───────────────────────
        if self._is_retry_exhausted(steps_done):
            retry_count = self._count_retries(steps_done)
            logger.warning(
                "Policy fallback: retry exhausted (retry_count=%d, RETRY_MAX=%d) → '%s'",
                retry_count, self.retry_max, FALLBACK_NODE,
            )
            return FALLBACK_NODE

        # ── Fallback 4: Max steps reached ─────────────────────
        if len(steps_done) >= self.max_steps:
            logger.warning(
                "Policy fallback: max steps reached (%d >= %d) → '%s'",
                len(steps_done), self.max_steps, FALLBACK_NODE,
            )
            return FALLBACK_NODE

        # ── ENFORCE: Transparent passthrough ───────────────────
        # Policy NEVER routes intent=A to next_node=B unless fallback to chat

        if intent in INTENT_NODE_MAP:
            next_node = INTENT_NODE_MAP[intent]
            logger.debug("Policy: intent='%s' → node='%s' (passthrough)", intent, next_node)
            return next_node

        # Unknown intent → fallback
        logger.warning(
            "Policy: unknown intent='%s', falling back to '%s'", intent, FALLBACK_NODE,
        )
        return FALLBACK_NODE

    # ── Helpers ─────────────────────────────────────────────────

    def _is_retry_exhausted(self, steps_done: list[str]) -> bool:
        """Check if any node has been retried more than RETRY_MAX times."""
        return self._count_retries(steps_done) >= self.retry_max

    @staticmethod
    def _count_retries(steps_done: list[str]) -> int:
        """Count how many times the most-repeated node has been retried.

        First execution of a node is not a retry, so count = max_freq - 1.
        Example: ["search", "search", "search"] → retry count = 2.
        """
        if not steps_done:
            return 0
        counts = Counter(steps_done)
        max_freq = max(counts.values())
        return max_freq - 1

    # ── Properties ───────────────────────────────────────────────

    @property
    def max_steps_limit(self) -> int:
        return self.max_steps

    @property
    def retry_max_limit(self) -> int:
        return self.retry_max

    @property
    def confidence_fallback_threshold(self) -> float:
        return self.confidence_threshold
