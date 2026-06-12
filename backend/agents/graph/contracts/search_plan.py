"""
SearchPlan v2 — unified contract between ConstraintParser and all downstream nodes.

A single SearchPlan is produced by ConstraintParser and consumed by:
  - orchestrator (routing decision)
  - entry_router (skip classification when intent is explicit)
  - search_node (structured sort vs semantic)
  - ranking/merge (budget_band as soft feature)
  - frontend (hint signals)

v2 changes: added intent / budget_band / category_filter / hint flags.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal


# ── Valid sort fields (schema constraint) ──────────────────────

VALID_SORT_FIELDS = {
    "price",
    "created_at",
    "popularity",
    "rating",
    "relevance",
}

VALID_DIRECTIONS = {"asc", "desc"}


# ── Strategy enum ──────────────────────────────────────────────

class RetrievalStrategy:
    STRUCTURED_SORT = "structured_sort"   # SQL ORDER BY
    SEMANTIC = "semantic"                 # FAISS + RRF
    HYBRID = "hybrid"                     # both + merge


# ── Intent taxonomy (v2) ───────────────────────────────────────

class QueryIntent:
    SORT = "sort"              # Hard constraint: SQL ORDER BY directly
    RECOMMEND = "recommend"    # Soft constraint: RAG + ranking + hints
    AMBIGUOUS = "ambiguous"    # Unclear: soft recommend + clarify hint

VALID_INTENTS = {QueryIntent.SORT, QueryIntent.RECOMMEND, QueryIntent.AMBIGUOUS}


# ── Sort pattern definitions (shared with ConstraintParser) ───

# (regex, sort_by, direction, optional_intent_override)
SORT_PATTERNS: list[tuple[str, str, str]] = [
    # Price
    (r"最贵|贵.{0,2}(排前|在前)|价格.{0,2}高.*低|expensive|price.{0,5}desc|highest.*price", "price", "desc"),
    (r"最便宜|便宜|cheap|价格.{0,2}低.*高|lowest.*price|price.{0,5}asc", "price", "asc"),
    # Rating
    (r"评分|评价.*高|高分|rating|highest.*rat|best.*rat", "rating", "desc"),
    # Recency
    (r"最新|newest|latest|最近.*上|刚.*上|new.*arrival", "created_at", "desc"),
    # Popularity
    (r"最火|热门|popular|hot|trending|畅销|best.*sell", "popularity", "desc"),
]

# Budget extraction patterns: (regex, band_label)
BUDGET_PATTERNS: list[tuple[str, str]] = [
    (r"(\d+)[\-~到](\d+)", None),              # "1000-3000" → parsed dynamically
    (r"(?:under|below|under)\s*\$?(\d+)", None),  # "under 500"
    (r"(?:within|budget|预算)\s*\$?(\d+)", None),  # "within 500"
    (r"(\d+)\s*(?:以内|以下)", None),             # "500以内"
]

# Category hint keywords (extracted from query for filter)
CATEGORY_KEYWORDS: dict[str, str] = {
    "耳机": "耳机",
    "headphone": "耳机",
    "headset": "耳机",
    "手机": "智能手机",
    "phone": "智能手机",
    "电脑": "笔记本电脑",
    "laptop": "笔记本电脑",
    "显示器": "显示器",
    "屏幕": "显示器",
    "monitor": "显示器",
    "键盘": "键盘",
    "keyboard": "键盘",
    "鼠标": "鼠标",
    "mouse": "鼠标",
    "手表": "智能手表",
    "watch": "智能手表",
    "充电宝": "充电宝",
    "移动电源": "充电宝",
    "powerbank": "充电宝",
    "椅子": "椅子",
    "chair": "椅子",
    "电竞": "电竞",
    "gaming": "电竞",
}

BRAND_ALIASES: dict[str, str] = {
    "苹果": "苹果",
    "华为": "华为",
    "小米": "小米",
    "三星": "三星",
    "索尼": "索尼",
    "戴尔": "戴尔",
    "dell": "戴尔",
    "Dell": "戴尔",
    "联想": "联想",
    "罗技": "罗技",
    "logitech": "罗技",
    "Logitech": "罗技",
    "apple": "苹果",
    "Apple": "苹果",
    "huawei": "华为",
    "Huawei": "华为",
    "xiaomi": "小米",
    "Xiaomi": "小米",
    "samsung": "三星",
    "Samsung": "三星",
    "sony": "索尼",
    "Sony": "索尼",
    "lenovo": "联想",
    "Lenovo": "联想",
}

# Recommend-trigger keywords (if present → intent=recommend)
RECOMMEND_TRIGGERS: list[str] = [
    r"推荐", r"recommend", r"suggest", r"建议", r"帮我选",
    r"买什么", r"选.*哪个", r"哪个.*好", r"适合",
]


# ── Query normalization ────────────────────────────────────────

from ..utils import normalize_query  # canonical implementation, re-exported here


# ── Budget band parsing ────────────────────────────────────────

def parse_budget_band(amount: int, is_lower_bound: bool = False) -> str:
    """Map a number to a budget band label.

    is_lower_bound=False: "X元以内" style → amount is upper bound.
    is_lower_bound=True:  "X元以上" style → amount is lower bound.
    """
    if is_lower_bound:
        if amount >= 1500:
            return "1500+"
        elif amount >= 500:
            return "500+"
        return "0+"
    else:
        if amount <= 500:
            return "0-500"
        elif amount <= 1500:
            return "500-1500"
        else:
            return "1500+"


def parse_budget_range(amount: int, is_lower_bound: bool = False) -> tuple[Optional[float], Optional[float]]:
    """Parse budget into numeric range for SQL filtering.
    
    is_lower_bound=False: "500以内" → (None, 500 * 1.3)
    is_lower_bound=True:  "1000以上" → (1000 * 0.7, None)
    Returns (lower, upper) with soft margins.
    """
    if is_lower_bound:
        return (amount * 0.7, None)
    else:
        return (None, amount * 1.3)


# ── SearchPlan v2 ──────────────────────────────────────────────

@dataclass
class SearchPlan:
    """Unified query plan produced by ConstraintParser.

    This is the single source of truth for all downstream routing,
    retrieval, ranking, and UI hint decisions.
    """

    # ── Routing ──
    intent: str = QueryIntent.RECOMMEND   # "sort" | "recommend" | "ambiguous"

    # ── Hard constraint (when intent=sort) ──
    sort_by: Optional[str] = None          # "price" | "rating" | "popularity" | "created_at"
    direction: Optional[str] = None        # "asc" | "desc"
    category_filter: Optional[str] = None  # e.g. "headphones" — direct SQL WHERE
    brand: Optional[str] = None            # brand filter (Apple/Huawei/etc)
    budget_lower: Optional[float] = None   # price lower bound (actual numeric)
    budget_upper: Optional[float] = None   # price upper bound (actual numeric)

    # ── Constraint confidence (0.0-1.0) ──
    # ≥ 0.9 → hard SQL WHERE filter
    # < 0.9 → soft boost in ranking (不进 SQL, 作为 _rank_products 加分项)
    category_confidence: float = 1.0

    # ── Soft constraint (consumed by ranking phase) ──
    budget_band: Optional[str] = None      # "0-500" | "500-1500" | "1500+" | None

    # ── Search strategy ──
    strategy: str = RetrievalStrategy.SEMANTIC
    semantic_query: str = ""

    # ── UX hints (not logic) ──
    show_clarify_hint: bool = False
    show_budget_hint: bool = False

    # ── Trace ──
    method: str = "regex"                  # "regex" | "llm" | "none"
    detail: str = ""

    # ── Queries ────────────────────────────────────────────────

    def is_structured(self) -> bool:
        """True when this plan calls for direct SQL ORDER BY."""
        return (
            self.sort_by is not None
            and self.direction is not None
        )

    def is_ambiguous(self) -> bool:
        """True when the intent is not a specific commerce intent.
        
        Handles both old QueryIntent.AMBIGUOUS and new IntentClassifier intents.
        """
        return (
            self.intent == getattr(QueryIntent, "AMBIGUOUS", "ambiguous")
            or self.intent not in {"search", "recommend", "order", "analytics"}
        )

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "strategy": self.strategy,
            "sort_by": self.sort_by,
            "direction": self.direction,
            "category_filter": self.category_filter,
            "brand": self.brand,
            "budget_lower": self.budget_lower,
            "budget_upper": self.budget_upper,
            "budget_band": self.budget_band,
            "category_confidence": self.category_confidence,
            "show_clarify_hint": self.show_clarify_hint,
            "show_budget_hint": self.show_budget_hint,
            "method": self.method,
            "detail": self.detail,
        }

    def to_phase(self) -> dict:
        """Render as a trace phase for SessionTrace / Decision Cards."""
        if self.is_structured():
            detail = f"SQL ORDER BY {self.sort_by} {self.direction.upper()} LIMIT 10"
            label = f"SQL排序检索 ({self.sort_by} {self.direction})"
        elif self.strategy == RetrievalStrategy.HYBRID:
            detail = "FAISS向量 + SQL LIKE → RRF融合"
            label = "混合检索"
        else:
            detail = f"FAISS语义检索: {self.semantic_query}"
            label = "语义向量检索"
        return {"phase": "searching", "label": label, "detail": detail}


# ── QueryFrame (Layer 1 standard input) ────────────────────────

@dataclass
class QueryFrame:
    """Standardized input frame for Commerce Layer (Layer 1).

    Single source of truth passed from orchestrator to all Layer 1 components.
    Prevents multiple layers from re-interpreting/rewriting the query independently.
    """
    raw: str                        # original user query
    normalized: str                 # normalized query (fullwidth to halfwidth, etc.)
    intent: object                  # IntentResult from IntentClassifier
    context: dict = field(default_factory=dict)  # control_context from State Router
    state_version: str = "v1"       # for trace/debug/replay alignment
    trace_id: str = ""              # end-to-end trace anchor


# ── CommerceResult (Layer 1 unified output) ────────────────────

@dataclass
class CommerceResult:
    """Unified return type for Commerce Layer processing.

    When degraded=True, plan is None and orchestrator falls back to lightweight path.
    """
    intent: object                  # IntentResult
    plan: SearchPlan | None = None  # None when confidence too low
    degraded: bool = False          # True when plan could not be produced
