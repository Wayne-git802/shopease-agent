"""
Product Domain Schema — defines valid clarification slots for product recommendation.

This is a declaration of what information the system may need before making
personalized recommendations.  Each slot has a priority (required/optional)
and valid value ranges for filtering.
"""

from pydantic import BaseModel, Field


class SlotDef(BaseModel):
    """Definition of one clarification slot."""
    key: str                     # e.g. "budget"
    label: str                   # e.g. "预算"
    question: str                # e.g. "你的预算是多少？"
    priority: str = "optional"   # "required" | "optional"
    options: list[str] = []      # pre-defined choices, e.g. ["0-1000", "1000-3000", "3000+"]
    filter_field: str = ""       # Django ORM field for filtering (e.g. "price__lte")


def _get_budget_options() -> list[str]:
    """Get budget options dynamically from price distribution."""
    try:
        from .budget_tiers import get_budget_options
        return get_budget_options()
    except Exception:
        return ["¥0 - ¥20", "¥20 - ¥50", "¥50 - ¥100", "¥100 - ¥200", "¥200+"]


# ── Product Recommendation Domain ─────────────────────────────────

PRODUCT_DOMAIN_SLOTS: list[SlotDef] = [
    SlotDef(
        key="budget",
        label="预算",
        question="你的预算是多少？",
        priority="required",
        options=_get_budget_options(),  # Dynamic from price distribution
        filter_field="price",
    ),
    SlotDef(
        key="use_case",
        label="用途",
        question="主要用途是什么？",
        priority="optional",
        options=["办公学习", "游戏娱乐", "摄影设计", "日常使用"],
        filter_field="",
    ),
    SlotDef(
        key="brand",
        label="品牌偏好",
        question="有品牌偏好吗？",
        priority="optional",
        options=["华为", "苹果", "小米", "三星", "不限"],
        filter_field="",
    ),
]

# Fast lookup
SLOT_BY_KEY: dict[str, SlotDef] = {s.key: s for s in PRODUCT_DOMAIN_SLOTS}
REQUIRED_SLOTS = [s for s in PRODUCT_DOMAIN_SLOTS if s.priority == "required"]

# Max clarify rounds before giving up
MAX_CLARIFY_ROUNDS = 1
