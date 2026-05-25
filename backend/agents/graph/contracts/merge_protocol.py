"""
Merge Policy Protocol — contract for parallel-node output fusion.

Nodes produce signals in different semantic spaces (retrieval relevance,
recommendation scores). MergePolicy normalizes and fuses them into a
single ranked list.
"""
from abc import ABC, abstractmethod

from ..state import AgentState, ProductRef, RankedItem


class MergePolicyProtocol(ABC):
    """Abstract merge interface.

    The standard pipeline is:
      Step 1: normalize each signal space → [0, 1]
      Step 2: late fusion (weighted sum in unified space)
      Step 3: re-rank (MMR diversity boost or custom scorer)

    Contract:
      - merge(state) → state (modified in place, ranked_items populated)
      - Configurable weights and diversity lambda.
    """

    SEARCH_WEIGHT: float = 0.3
    REC_WEIGHT: float = 0.7
    DIVERSITY_LAMBDA: float = 0.3

    @abstractmethod
    def merge(self, state: AgentState) -> AgentState:
        """Consume state.retrieved_products + state.ranked_items,
        produce state.ranked_items (deduped, fused, re‑ranked).
        Returns the modified state."""

    @staticmethod
    @abstractmethod
    def normalize(scores: dict[int, float]) -> dict[int, float]:
        """Min‑max normalization → [0, 1]."""

    @staticmethod
    @abstractmethod
    def fuse(search_scores: dict[int, float],
             rec_scores: dict[int, float]) -> dict[int, float]:
        """Late fusion: weighted sum."""

    @staticmethod
    @abstractmethod
    def rerank(fused: list[tuple[int, float]], lambda_param: float = 0.3
               ) -> list[tuple[int, float]]:
        """MMR‑style diversity re‑rank."""
