"""
Evaluation Hooks — offline quality metrics for search and recommend nodes.

Usage:
    from agents.graph.eval import eval_search_node, eval_recommend_node

    metrics = eval_search_node(output, ground_truth_ids)
    → {"recall@10": 0.85, "precision@5": 0.72}

    diversity = eval_recommend_node(ranked_items)
    → {"diversity": 0.65}
"""
from .state import ProductRef, RankedItem
from .contracts import SearchNodeOutput, RecommendNodeOutput


def recall_at_k(retrieved_ids: list[int], relevant_ids: set[int], k: int) -> float:
    """Fraction of relevant items that appear in top-k results."""
    if not relevant_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / len(relevant_ids)


def precision_at_k(retrieved_ids: list[int], relevant_ids: set[int], k: int) -> float:
    """Fraction of top-k results that are relevant."""
    if k == 0:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & relevant_ids) / k


def eval_search_node(output: SearchNodeOutput,
                     ground_truth: list[int]) -> dict[str, float]:
    """Evaluate search node output against ground-truth product IDs."""
    retrieved = [p.id for p in output.products]
    relevant = set(ground_truth)

    return {
        "recall@10": recall_at_k(retrieved, relevant, 10),
        "recall@5": recall_at_k(retrieved, relevant, 5),
        "precision@10": precision_at_k(retrieved, relevant, 10),
        "precision@5": precision_at_k(retrieved, relevant, 5),
        "num_retrieved": len(retrieved),
        "num_relevant": len(relevant),
    }


def diversity_score(items: list[RankedItem], categories: dict[int, str]) -> float:
    """Category diversity in top-k: 1 - (max_category_count / k)."""
    if not items:
        return 0.0
    cat_counts: dict[str, int] = {}
    for item in items:
        cat = categories.get(item.id, "unknown")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    max_count = max(cat_counts.values()) if cat_counts else len(items)
    return 1.0 - (max_count / len(items))


def eval_recommend_node(output: RecommendNodeOutput,
                        categories: dict[int, str] | None = None) -> dict[str, float]:
    """Evaluate recommend node: diversity, score distribution."""
    cats = categories or {}
    return {
        "diversity": diversity_score(output.ranked_items, cats),
        "num_items": len(output.ranked_items),
        "mean_score": (
            sum(r.score for r in output.ranked_items) / max(len(output.ranked_items), 1)
        ),
        "score_std": _std([r.score for r in output.ranked_items]),
    }


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
