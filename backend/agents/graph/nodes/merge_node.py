"""
Merge Node — P1 Policy-Aware Reranker.

Upgrades the old fixed-weight fusion (0.3 search / 0.7 rec) to:

1. Unified Candidate Contract
   ── Every result from search/recommend enters as a Candidate with
   explicit score_type + source, enabling correct normalization.

2. Intent-Aware Merge Policy
   ── Different query types use different weight distributions and
   re-rank objectives (diversity, relevance, personalization).

3. Per-Source Score Normalization
   ── Structured SQL scores, FAISS similarity scores, and CF scores
   are normalized within their own spaces before fusion.

4. Strategy-Policy Compatibility
   ── Merge policy is downgraded (not rejected) when incompatible
   with the selected search strategy.

Architecture (P1):
  search_node   →  Candidate groups (structured + semantic)
  recommend_node →  Candidate group (cf/popular/for-you)
                      │
                      ▼
  merge_node (HERE):
    Step 1: Build unified Candidate list
    Step 2: Normalize per score_type
    Step 3: Apply intent-aware weights
    Step 4: Diversity re-rank (MMR)
    Step 5: Output RankedItem list
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal

from ..state import AgentState, RankedItem


# ═══════════════════════════════════════════════════════════════
# Unified Candidate Contract
# ═══════════════════════════════════════════════════════════════

@dataclass
class Candidate:
    """Single result item from any source, with score metadata.

    All scores are in their NATIVE space — merge_node normalizes per
    score_type before fusion.
    """
    id: int
    score: float                              # native score
    score_type: str                           # "structured_sort" | "semantic" | "cf" | "popular"
    source: str                               # "search" | "recommend"
    score_confidence: float = 1.0             # 0-1, how reliable is this score?
    name: str = ""
    price: float = 0.0
    category: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "score": self.score,
            "score_type": self.score_type,
            "source": self.source,
            "score_confidence": self.score_confidence,
            "name": self.name,
            "price": self.price,
            "category": self.category,
        }


# ═══════════════════════════════════════════════════════════════
# Merge Policy Config
# ═══════════════════════════════════════════════════════════════

# Intent → (search_weight, rec_weight, diversity_lambda)
# Higher diversity_lambda → more diverse results
MERGE_POLICIES: dict[str, dict[str, float]] = {
    "search": {
        "search_weight": 0.70,
        "rec_weight": 0.30,
        "diversity_lambda": 0.20,
    },
    "recommend": {
        "search_weight": 0.20,
        "rec_weight": 0.80,
        "diversity_lambda": 0.35,
    },
    "order": {
        "search_weight": 0.90,
        "rec_weight": 0.10,
        "diversity_lambda": 0.05,
    },
    "chat": {
        "search_weight": 0.50,
        "rec_weight": 0.50,
        "diversity_lambda": 0.25,
    },
    "analytics": {
        "search_weight": 0.95,
        "rec_weight": 0.05,
        "diversity_lambda": 0.0,
    },
    # fallback
    "default": {
        "search_weight": 0.50,
        "rec_weight": 0.50,
        "diversity_lambda": 0.25,
    },
}

# Strategy → allowed merge policies (for compatibility downgrade)
# If current merge policy key is NOT in the allowed list, downgrade to first.
STRATEGY_POLICY_COMPAT: dict[str, list[str]] = {
    "sql_only":  ["search", "order", "analytics", "default"],
    "semantic":  ["search", "recommend", "chat", "default"],
    "hybrid":    ["search", "recommend", "order", "chat", "analytics", "default"],
    # unknown: allow all
}


# ═══════════════════════════════════════════════════════════════
# Normalization
# ═══════════════════════════════════════════════════════════════

def _normalize_group(candidates: list[Candidate]) -> list[Candidate]:
    """Min-max normalize scores within a group (same score_type)."""
    if not candidates:
        return candidates

    scores = [c.score for c in candidates]
    lo, hi = min(scores), max(scores)

    if hi == lo:
        for c in candidates:
            c.score = 0.5
        return candidates

    for c in candidates:
        c.score = (c.score - lo) / (hi - lo)
    return candidates


def _normalize_per_type(candidates: list[Candidate]) -> list[Candidate]:
    """Group candidates by score_type, normalize each group independently."""
    groups: dict[str, list[Candidate]] = {}
    for c in candidates:
        groups.setdefault(c.score_type, []).append(c)

    result = []
    for group in groups.values():
        result.extend(_normalize_group(group))
    return result


# ═══════════════════════════════════════════════════════════════
# Fusion
# ═══════════════════════════════════════════════════════════════

def _fuse(
    candidates: list[Candidate],
    search_weight: float,
    rec_weight: float,
) -> dict[int, float]:
    """Weighted sum per product_id, respecting source weights."""
    fused: dict[int, tuple[float, float]] = {}  # id → (total_weighted, total_confidence)

    for c in candidates:
        source_w = search_weight if c.source == "search" else rec_weight
        adjusted = c.score * source_w * c.score_confidence

        if c.id not in fused:
            fused[c.id] = (adjusted, c.score_confidence)
        else:
            prev_score, prev_conf = fused[c.id]
            # Take the better score if same product from multiple sources
            if adjusted > prev_score:
                fused[c.id] = (adjusted, max(prev_conf, c.score_confidence))

    return {pid: s for pid, (s, _) in fused.items()}


# ═══════════════════════════════════════════════════════════════
# MMR Re-rank
# ═══════════════════════════════════════════════════════════════

def _rerank_mmr(
    scored: list[tuple[int, float]],
    candidates: list[Candidate],
    lambda_param: float = 0.3,
) -> list[tuple[int, float]]:
    """MMR: maximize relevance - lambda * max_similarity_to_selected.

    Similarity = same category → penalty (simple for now).
    """
    if len(scored) <= 1:
        return scored

    # Build category lookup
    cat_map: dict[int, str] = {}
    for c in candidates:
        if c.category:
            cat_map[c.id] = c.category

    selected: list[tuple[int, float]] = []
    remaining = dict(scored)  # id → score

    # First item: highest score
    first_id = max(remaining, key=remaining.get)  # type: ignore[arg-type]
    selected.append((first_id, remaining.pop(first_id)))

    while remaining and len(selected) < 20:
        best_id, best_score = None, -1.0
        for pid, score in remaining.items():
            # Diversity penalty: if same category as any selected item
            penalty = 0.0
            if lambda_param > 0 and cat_map:
                pid_cat = cat_map.get(pid, "")
                for sel_id, _ in selected:
                    sel_cat = cat_map.get(sel_id, "")
                    if pid_cat and sel_cat and pid_cat == sel_cat:
                        penalty = lambda_param
                        break

            adjusted = score - penalty
            if adjusted > best_score:
                best_score = adjusted
                best_id = pid

        if best_id is None:
            break
        selected.append((best_id, remaining.pop(best_id)))

    return selected


# ═══════════════════════════════════════════════════════════════
# Policy compatibility check
# ═══════════════════════════════════════════════════════════════

def _resolve_merge_policy(
    intent: str,
    strategy: str,
) -> tuple[str, bool]:
    """Resolve merge policy, downgrading if incompatible with strategy.

    Returns:
        (effective_policy_key, downgraded: bool)
    """
    # Determine merge policy from intent
    policy_key = intent if intent in MERGE_POLICIES else "default"

    # Check compatibility
    allowed = STRATEGY_POLICY_COMPAT.get(strategy, STRATEGY_POLICY_COMPAT["hybrid"])
    if policy_key in allowed:
        return policy_key, False

    # Downgrade to first allowed policy
    downgraded_key = allowed[0] if allowed else "default"
    return downgraded_key, True


# ═══════════════════════════════════════════════════════════════
# Main merge function
# ═══════════════════════════════════════════════════════════════

def merge(state: AgentState, strategy: str = "semantic") -> AgentState:
    """
    P1 Policy-Aware merge.

    1. Build Candidate list from retrieved_products + ranked_items
    2. Normalize per score_type
    3. Apply intent-aware weights
    4. Diversity re-rank
    5. Output ranked_items

    Args:
        state: AgentState with retrieved_products + ranked_items populated
        strategy: SearchStrategy used by search_node ("sql_only"|"semantic"|"hybrid")

    Returns:
        Modified state with ranked_items set.
    """
    # ── Step 0: Merge policy resolution ─────────────────────
    intent = state.intent or "chat"
    policy_key, policy_downgraded = _resolve_merge_policy(intent, strategy)
    policy = MERGE_POLICIES.get(policy_key, MERGE_POLICIES["default"])

    # ── Step 1: Build Candidate list ────────────────────────
    candidates: list[Candidate] = []

    # search results → structured_sort or semantic
    search_plan_dict = state.parallel_results.get("_search_plan", {})
    search_strategy = search_plan_dict.get("strategy", "semantic")

    for p in state.retrieved_products or []:
        score_type = "structured_sort" if search_strategy == "structured_sort" else "semantic"
        candidates.append(Candidate(
            id=p.id,
            score=p.relevance,
            score_type=score_type,
            source="search",
            score_confidence=0.9 if search_strategy == "structured_sort" else 0.7,
            name=p.name,
            price=p.price,
            category=p.category,
        ))

    # recommend results → cf or popular
    rec_type = state.parallel_results.get("recommend_type", "popular")
    rec_confidence = 0.6 if rec_type == "popular" else 0.75

    for r in (state.ranked_items or []):
        # Look up name/category from tool_results
        name, price_val, category = "", 0.0, ""
        for pr in state.tool_results.get("products", []):
            pid = pr.get("product_id") or pr.get("id", 0)
            if pid == r.id:
                name = str(pr.get("name", pr.get("product_name", "")))
                try:
                    price_val = float(pr.get("price", 0))
                except (ValueError, TypeError):
                    price_val = 0.0
                category = str(pr.get("category", pr.get("category_name", "")))
                break

        candidates.append(Candidate(
            id=r.id,
            score=r.score,
            score_type="cf" if rec_type == "for-you" else "popular",
            source="recommend",
            score_confidence=rec_confidence,
            name=name,
            price=price_val,
            category=category,
        ))

    if not candidates:
        state.current_node = "merge"
        state.steps_done.append("merge")
        return state

    # ── Step 2: Normalize per score_type ────────────────────
    candidates = _normalize_per_type(candidates)

    # ── Step 3: Fuse with intent-aware weights ──────────────
    fused = _fuse(candidates, policy["search_weight"], policy["rec_weight"])

    # ── Step 4: Diversity re-rank ───────────────────────────
    scored_list = sorted(fused.items(), key=lambda x: x[1], reverse=True)
    ranked = _rerank_mmr(
        scored_list, candidates,
        lambda_param=policy["diversity_lambda"],
    )

    # ── Step 5: Output ──────────────────────────────────────
    state.ranked_items = [
        RankedItem(id=pid, score=round(sc, 4), source="fusion")
        for pid, sc in ranked[:20]
    ]

    # ── UI message ──────────────────────────────────────────
    n = len(state.ranked_items)
    source_label = (
        f"SQL优先" if strategy == "sql_only"
        else f"语义优先" if strategy == "semantic"
        else "混合检索"
    )
    downgrade_note = " (策略降级)" if policy_downgraded else ""
    state.ui_message = (
        f"{source_label} → 融合 {n} 条结果{downgrade_note}"
    )

    # ── Score distribution for trace ─────────────────────────
    state.score_distribution = {
        "search_mean": policy["search_weight"],
        "rec_mean": policy["rec_weight"],
        "diversity": policy["diversity_lambda"],
        "candidate_count": float(len(candidates)),
        "fused_count": float(len(fused)),
        "final_count": float(n),
    }
    # Store non-float merge metadata for DecisionTrace
    state.parallel_results["_merge_policy"] = {
        "policy": policy_key,
        "downgraded": policy_downgraded,
        "search_weight": policy["search_weight"],
        "rec_weight": policy["rec_weight"],
        "diversity_lambda": policy["diversity_lambda"],
    }

    state.current_node = "merge"
    state.steps_done.append("merge")
    return state


def merge_node(state: AgentState) -> AgentState:
    """LangGraph node wrapper — reads strategy from state."""
    strategy = state.parallel_results.get("_search_strategy", "semantic")
    return merge(state, strategy=strategy)
