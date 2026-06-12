"""
AgentState — SSOT (Single Source of Truth) for the LangGraph system.

Every node reads/writes ONLY this state. No hidden coupling.
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, model_validator


# ── Sub-types ─────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str          # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ProductRef(BaseModel):
    model_config = {"extra": "allow"}
    id: int
    name: str
    price: float
    category: str = ""
    relevance: float = 0.0      # retrieval score [0,1]


class DocRef(BaseModel):
    model_config = {"populate_by_name": True, "extra": "ignore"}
    id: str = Field(alias="doc_id")
    content: str
    source: str = ""
    relevance: float = 0.0
    
    @model_validator(mode="before")
    @classmethod
    def _normalize_input(cls, data: Any) -> Any:
        """Convert doc_id → id for backward compatibility with serialized state."""
        if isinstance(data, dict):
            if "doc_id" in data and "id" not in data:
                data = dict(data)
                data["id"] = data.pop("doc_id")
        return data


class RankedItem(BaseModel):
    id: int
    score: float                # fusion score [0,1]
    source: str = "fusion"      # "search" | "recommend" | "fusion"
    reasons: list[str] = []     # 🆕 P3: human-readable recommendation reasons


class PurchaseSummary(BaseModel):
    total_orders: int = 0
    avg_order_value: float = 0.0
    top_categories: list[str] = []
    last_purchase_date: datetime | None = None


class BehavioralProfile(BaseModel):
    browse_depth: float = 0.0
    price_sensitivity: float = 0.5     # 0-1, lower = more sensitive
    return_rate: float = 0.0
    session_frequency: str = "weekly"  # "daily"|"weekly"|"monthly"


class UserMemory(BaseModel):
    user_id: int
    preferences: dict[str, float] = {}        # {category: decayed_score}
    preference_events: dict[str, list[tuple[float, datetime]]] = {}  # raw for decay calc
    embedding: list[float] | None = None
    purchase_summary: PurchaseSummary = Field(default_factory=PurchaseSummary)
    behavioral_profile: BehavioralProfile = Field(default_factory=BehavioralProfile)
    updated_at: datetime = Field(default_factory=datetime.now)


class NodeTrace(BaseModel):
    node_name: str
    model_name: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    cost: float = 0.0
    cache_hit: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


# ── ParallelResults — typed container replacing dict[str, Any] ──────

class ParallelResults(BaseModel):
    """Typed key:value store for all parallel execution context.

    Replaces the ad-hoc dict[str, Any] that accumulated 30+ untyped keys.
    Every field has a default so nodes only set what they need.
    """
    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def _normalize_keys(cls, data: Any) -> Any:
        """Map old '_underscored' dict keys to clean attribute names."""
        if isinstance(data, dict):
            remapped = {}
            extras = {}
            for k, v in data.items():
                clean = k.lstrip("_") if k.startswith("_") else k
                if clean in cls.model_fields:
                    remapped[clean] = v
                else:
                    extras[k] = v
            remapped.update(extras)
            return remapped
        return data

    # ── Search plan ──
    search_plan: dict = Field(default_factory=dict)
    search_plan_raw: Any = None
    search_phase_detail: str = ""
    search_phase_label: str = ""

    # ── Retrieval ──
    retrieval_mode: str = ""
    search_top_k: int = 10
    search_strategy: str = ""
    search_strategy_decision: dict = Field(default_factory=dict)
    score_breakdown: list = Field(default_factory=list)
    structured_products: list = Field(default_factory=list)

    # ── Constraints ──
    relaxed_constraints: list = Field(default_factory=list)
    no_results: bool = False

    # ── Reference resolution ──
    resolved_ref: Any = None
    clarify_reference: bool = False
    clarify_answer: str = ""
    collected_slots: dict = Field(default_factory=dict)

    # ── UX hints ──
    show_budget_hint: bool = False
    show_clarify_hint: bool = False
    llm_explanation: str = ""

    # ── Validation / trace ──
    validator_decisions: dict = Field(default_factory=dict)
    decision_trace: Any = None
    feedback_categories: list = Field(default_factory=list)

    # ── Signals ──
    conversation_signals: dict = Field(default_factory=dict)
    intent_score: dict = Field(default_factory=dict)

    # ── Routing context ──
    query_type: str = ""
    recommend_type: str = ""
    similar_product_id: str = ""
    display_id: str = ""

    # ── Order / analytics context ──
    order_action: str = ""
    order_id: int | None = None
    analytics_days: int = 7

    # ── Backward-compatible dict access ──
    @staticmethod
    def _key_to_attr(key: str) -> str:
        return key.lstrip("_")

    def __getitem__(self, key: str):
        return getattr(self, self._key_to_attr(key))

    def __setitem__(self, key: str, value) -> None:
        setattr(self, self._key_to_attr(key), value)

    def get(self, key: str, default=None):
        return getattr(self, self._key_to_attr(key), default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, self._key_to_attr(key))


# ── Main State ────────────────────────────────────────────────────

class AgentState(BaseModel):
    """SSOT — all nodes read/write only this."""

    # Input
    user_query: str = ""
    session_id: str = ""
    user_id: int | None = None
    history: list[ChatMessage] = []

    # Routing
    intent: str = ""
    confidence: float = 0.0
    routing_method: str = ""

    # Model selection
    model_name: str = ""

    # Retrieval (RAG)
    retrieved_products: list[ProductRef] = []
    retrieved_docs: list[DocRef] = []

    # Long-term memory
    user_memory: UserMemory | None = None

    # Execution
    current_node: str = ""
    ui_message: str = ""
    steps_done: list[str] = []
    tool_results: dict[str, Any] = {}
    parallel_results: ParallelResults = Field(default_factory=ParallelResults)

    # Normalized query (for caching / sort detection)
    normalized_query: str = ""

    # Recommendation
    ranked_items: list[RankedItem] = []
    score_distribution: dict[str, float] = {}   # {source: mean_score}

    # 🆕 P3: Conversational clarification
    missing_fields: list[str] = []      # slots to ask about, e.g. ["budget"]
    clarify_round: int = 0              # current round (max = MAX_CLARIFY_ROUNDS)

    # Layer 0: Route control context (resolved slots, trace_id, domain)
    control_context: dict = Field(default_factory=dict)

    # Output
    final_response: str = ""
    error: str | None = None

    # Version
    graph_version: str = "v1"

    # Observability
    trace: list[NodeTrace] = []
