"""
AgentState — SSOT (Single Source of Truth) for the LangGraph system.

Every node reads/writes ONLY this state. No hidden coupling.
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# ── Sub-types ─────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str          # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ProductRef(BaseModel):
    id: int
    name: str
    price: float
    category: str = ""
    relevance: float = 0.0      # retrieval score [0,1]


class DocRef(BaseModel):
    id: str
    content: str
    source: str = ""
    relevance: float = 0.0


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


# ── Main State ────────────────────────────────────────────────────

class AgentState(BaseModel):
    """SSOT — all nodes read/write only this."""

    # Input
    user_query: str = ""
    session_id: str = ""
    user_id: int | None = None
    history: list[ChatMessage] = []

    # Routing
    intent: str = ""              # "search"|"recommend"|"order"|"ops"|"chat"
    confidence: float = 0.0
    routing_method: str = ""      # "fast" | "slow"

    # Model selection (per-node, set by node itself via CostRouter)
    model_name: str = ""

    # Retrieval (RAG)
    retrieved_products: list[ProductRef] = []
    retrieved_docs: list[DocRef] = []

    # Long-term memory
    user_memory: UserMemory | None = None

    # Execution
    current_node: str = ""
    ui_message: str = ""                # human-readable cognitive status
    steps_done: list[str] = []
    tool_results: dict[str, Any] = {}
    parallel_results: dict[str, Any] = {}

    # Normalized query (for caching / sort detection)
    normalized_query: str = ""

    # Recommendation
    ranked_items: list[RankedItem] = []
    score_distribution: dict[str, float] = {}   # {source: mean_score}

    # 🆕 P3: Conversational clarification
    missing_fields: list[str] = []      # slots to ask about, e.g. ["budget"]
    clarify_round: int = 0              # current round (max = MAX_CLARIFY_ROUNDS)

    # Output
    final_response: str = ""
    error: str | None = None

    # Version
    graph_version: str = "v1"

    # Observability
    trace: list[NodeTrace] = []
