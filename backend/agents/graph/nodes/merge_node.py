"""
Merge Node — fuse parallel search + recommend outputs.

I/O Contract:
  Input:  MergeNodeInput (retrieved_products, ranked_items, parallel_results)
  Output: MergeNodeOutput (ranked_items, score_distribution)

Implements MergePolicyProtocol with 3-step pipeline:
  Step 1: normalize each signal space → [0, 1]
  Step 2: late fusion (weighted sum in unified space)
  Step 3: MMR re-rank for diversity
"""
from ..state import AgentState, RankedItem
from ..contracts.merge_protocol import MergePolicyProtocol


class MergePolicy(MergePolicyProtocol):
    SEARCH_WEIGHT = 0.3
    REC_WEIGHT = 0.7
    DIVERSITY_LAMBDA = 0.3

    def merge(self, state: AgentState) -> AgentState:
        # Collect signals
        search_scores = {p.id: p.relevance for p in state.retrieved_products}
        rec_scores = {r.id: r.score for r in state.ranked_items}

        if not search_scores and not rec_scores:
            state.current_node = "merge"
            state.steps_done.append("merge")
            return state

        # Step 1: normalize
        search_norm = self.normalize(search_scores)
        rec_norm = self.normalize(rec_scores)

        # Step 2: late fusion
        fused = self.fuse(search_norm, rec_norm)

        # Step 3: re-rank
        ranked = self.rerank(
            [(pid, score) for pid, score in fused.items()],
            lambda_param=self.DIVERSITY_LAMBDA,
        )

        state.ranked_items = [
            RankedItem(id=pid, score=score, source="fusion")
            for pid, score in ranked[:20]
        ]

        state.ui_message = f"融合 {len(state.ranked_items)} 条结果，正在去重排序…"

        state.score_distribution = {
            "search_mean": sum(search_norm.values()) / max(len(search_norm), 1),
            "rec_mean": sum(rec_norm.values()) / max(len(rec_norm), 1),
        }
        state.current_node = "merge"
        state.steps_done.append("merge")
        return state

    @staticmethod
    def normalize(scores: dict[int, float]) -> dict[int, float]:
        if not scores:
            return {}
        vals = list(scores.values())
        lo, hi = min(vals), max(vals)
        if hi == lo:
            return {k: 0.5 for k in scores}
        return {k: (v - lo) / (hi - lo) for k, v in scores.items()}

    @staticmethod
    def fuse(search_scores: dict[int, float],
             rec_scores: dict[int, float]) -> dict[int, float]:
        all_ids = set(search_scores) | set(rec_scores)
        fused = {}
        for pid in all_ids:
            s = search_scores.get(pid, 0.0)
            r = rec_scores.get(pid, 0.0)
            fused[pid] = MergePolicy.SEARCH_WEIGHT * s + MergePolicy.REC_WEIGHT * r
        return fused

    @staticmethod
    def rerank(fused: list[tuple[int, float]],
               lambda_param: float = 0.3) -> list[tuple[int, float]]:
        """MMR: maximize relevance - lambda * max_similarity_to_selected."""
        if len(fused) <= 1:
            return fused

        # For simplicity: just re-sort with a minor diversity penalty for same category
        # Full MMR would need category vectors; for now we just dedup+sort
        seen = set()
        result = []
        for pid, score in sorted(fused, key=lambda x: x[1], reverse=True):
            if pid not in seen:
                seen.add(pid)
                result.append((pid, score))
        return result


def merge_node(state: AgentState) -> AgentState:
    """LangGraph node wrapper."""
    policy = MergePolicy()
    return policy.merge(state)
