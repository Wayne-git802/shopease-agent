"""
Search Strategy Selector — decides retrieval strategy inside search_node.

Strategies (binary):
  SQL_ONLY  — Direct SQL ORDER BY (price/rating/recency/popularity)
  SEMANTIC  — FAISS vector search + RRF fusion

HYBRID removed in Phase 5.  merge_node was deleted in Phase 6, leaving HYBRID
as a bare concatenation of structured + semantic — which diluted sort results.
Replaced by tiered fallback: SQL → empty? → pure FAISS.  No mixing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts.search_plan import SearchPlan


class SearchStrategy:
    SQL_ONLY = "sql_only"
    SEMANTIC = "semantic"


@dataclass
class StrategyDecision:
    strategy: str
    reason: str
    confidence: float
    dual_source: bool = False

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "reason": self.reason,
            "confidence": self.confidence,
            "dual_source": self.dual_source,
        }


def select(
    plan: SearchPlan,
    commerce_confidence: float = 0.5,
    active_signals: int = 0,
    query: str = "",
) -> StrategyDecision:
    """Decide retrieval strategy.

    Rules (first match wins):

    0. Regex-detected structured sort → SQL_ONLY.
       Regex sort is reliable regardless of commerce confidence.
       (LLM-detected sorts skip this rule.)

    1. LLM-detected structured sort + high confidence + category → SQL_ONLY.

    2. LLM-detected structured sort + low confidence → SEMANTIC
       (LLM might have hallucinated the sort).

    3. Not structured → SEMANTIC.
    """
    is_structured = plan.is_structured()

    # ── Rule 0: Regex sort → always trust it ──
    if is_structured and plan.method == "regex":
        return StrategyDecision(
            strategy=SearchStrategy.SQL_ONLY,
            reason=(
                f"Regex sort ({plan.sort_by} {plan.direction}) "
                + (f"category '{plan.category_filter}'" if plan.category_filter else "no category")
                + " — bypassing commerce confidence"
            ),
            confidence=0.85,
            dual_source=False,
        )

    # ── Rule 1: LLM sort + high confidence + category → SQL_ONLY ──
    if is_structured and commerce_confidence > 0.65 and plan.category_filter:
        return StrategyDecision(
            strategy=SearchStrategy.SQL_ONLY,
            reason=(
                f"LLM sort ({plan.sort_by} {plan.direction}) "
                f"with category '{plan.category_filter}', "
                f"confidence {commerce_confidence:.2f} > 0.65"
            ),
            confidence=min(commerce_confidence, 0.95),
            dual_source=False,
        )

    # ── Rule 2: LLM sort but low confidence or no category → SEMANTIC ──
    # LLM can hallucinate sorts; without category anchoring we don't trust it.
    # The sort info is still available in SearchPlan for ranking if needed.
    if is_structured:
        return StrategyDecision(
            strategy=SearchStrategy.SEMANTIC,
            reason=(
                f"LLM sort ({plan.sort_by} {plan.direction}) "
                f"but insufficient confidence/category — SEMANTIC"
            ),
            confidence=0.5,
            dual_source=False,
        )

    # ── Rule 3: Not structured → SEMANTIC ──
    return StrategyDecision(
        strategy=SearchStrategy.SEMANTIC,
        reason="No structured sort plan — semantic search",
        confidence=0.7,
        dual_source=False,
    )
