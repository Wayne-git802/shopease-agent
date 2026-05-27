"""
Search Strategy Selector — P1 node-level strategy decision.

Decides which retrieval strategy to use inside search_node, replacing
the old binary "structured? → SQL : FAISS" with a 3-strategy system.

Strategies:
  SQL_ONLY   — Direct SQL ORDER BY (price/rating/recency)
  SEMANTIC   — FAISS vector search + RRF fusion
  HYBRID     — Both paths, producing two separate Candidate groups

Strategy selection is deterministic, based on:
  - SearchPlan (from ConstraintParser + ExecutionValidator)
  - Commerce confidence
  - User signal state
  - Query structure

Output: StrategyDecision with strategy name, reason, and confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal

from .contracts.search_plan import SearchPlan, RetrievalStrategy


# ═══════════════════════════════════════════════════════════════
# Strategy enum
# ═══════════════════════════════════════════════════════════════

class SearchStrategy:
    SQL_ONLY = "sql_only"       # Pure structured sort
    SEMANTIC = "semantic"       # Pure vector search
    HYBRID = "hybrid"           # Both paths, two Candidate groups


# ═══════════════════════════════════════════════════════════════
# StrategyDecision
# ═══════════════════════════════════════════════════════════════

@dataclass
class StrategyDecision:
    """Output of SearchStrategySelector — recorded in DecisionTrace."""
    strategy: str               # SearchStrategy value
    reason: str                 # Human-readable
    confidence: float           # 0-1, how strongly this strategy fits
    dual_source: bool = False   # True → search_node produces 2 Candidate groups

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "reason": self.reason,
            "confidence": self.confidence,
            "dual_source": self.dual_source,
        }


# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

# When plan is structured but confidence is in this range → HYBRID
HYBRID_CONFIDENCE_RANGE = (0.4, 0.65)

# Max signals before considering user "experienced" → SEMANTIC preferred
EXPERT_SIGNAL_THRESHOLD = 10


# ═══════════════════════════════════════════════════════════════
# Selector
# ═══════════════════════════════════════════════════════════════

def select(
    plan: SearchPlan,
    commerce_confidence: float = 0.5,
    active_signals: int = 0,
    query: str = "",
) -> StrategyDecision:
    """
    Decide retrieval strategy for search_node.

    Decision logic (ordered, first match wins):

    1. Plan is structured + high confidence (>0.65)
       + has category filter → SQL_ONLY (sort is reliable + category narrows)

    2. Plan is structured + moderate confidence (0.4-0.65)
       → HYBRID (structured sort possibly useful, but fall back to semantic)

    3. Plan is structured + low confidence (<0.4)
       → SEMANTIC (don't trust the structured sort)

    4. Plan is NOT structured:
       a. User has many signals (experienced) → SEMANTIC (trust implicit knowledge)
       b. Otherwise → SEMANTIC (default)

    5. Only go HYBRID via rule 2. HYBRID is expensive (2 queries) — use sparingly.

    Args:
        plan: Validated SearchPlan from ConstraintParser
        commerce_confidence: From Commerce Layer (L1)
        active_signals: Active user feedback signals (within window)
        query: Original user query (for reason text)

    Returns:
        StrategyDecision
    """
    is_structured = plan.is_structured()

    # ── Rule 1: Structured + high confidence + category → SQL_ONLY ──
    if is_structured and commerce_confidence > 0.65:
        if plan.category_filter:
            return StrategyDecision(
                strategy=SearchStrategy.SQL_ONLY,
                reason=(
                    f"Structured sort ({plan.sort_by} {plan.direction}) "
                    f"with category filter '{plan.category_filter}', "
                    f"commerce confidence {commerce_confidence:.2f} > 0.65"
                ),
                confidence=min(commerce_confidence, 0.95),
                dual_source=False,
            )
        # Structured but no category → HYBRID (keep semantic as safety net)
        return StrategyDecision(
            strategy=SearchStrategy.HYBRID,
            reason=(
                f"Structured sort ({plan.sort_by} {plan.direction}) "
                f"but no category filter — HYBRID for safety"
            ),
            confidence=commerce_confidence * 0.8,
            dual_source=True,
        )

    # ── Rule 2: Structured + moderate confidence → HYBRID ──
    if is_structured and HYBRID_CONFIDENCE_RANGE[0] <= commerce_confidence <= HYBRID_CONFIDENCE_RANGE[1]:
        return StrategyDecision(
            strategy=SearchStrategy.HYBRID,
            reason=(
                f"Structured sort ({plan.sort_by} {plan.direction}) "
                f"with moderate confidence {commerce_confidence:.2f} — HYBRID"
            ),
            confidence=commerce_confidence,
            dual_source=True,
        )

    # ── Rule 3: Structured + low confidence → SEMANTIC ──
    if is_structured and commerce_confidence < HYBRID_CONFIDENCE_RANGE[0]:
        return StrategyDecision(
            strategy=SearchStrategy.SEMANTIC,
            reason=(
                f"Structured sort ({plan.sort_by} {plan.direction}) "
                f"but low confidence {commerce_confidence:.2f} < {HYBRID_CONFIDENCE_RANGE[0]}"
            ),
            confidence=0.5,
            dual_source=False,
        )

    # ── Rule 4: Not structured — always SEMANTIC for now ──
    # (Future: could go HYBRID for expert users with many signals)
    return StrategyDecision(
        strategy=SearchStrategy.SEMANTIC,
        reason="No structured sort plan — semantic search",
        confidence=0.7,
        dual_source=False,
    )
