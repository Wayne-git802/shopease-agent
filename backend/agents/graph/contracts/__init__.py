"""
Node I/O Contracts — explicit input/output schema for every node.

Every node MUST declare:
  - Input model  (what it reads from AgentState)
  - Output model (what it writes back)
  - side_effects (what external systems it touches)

This is how we prevent implicit coupling between nodes.
"""
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel, Field

from ..state import (
    AgentState, ProductRef, DocRef, RankedItem,
    UserMemory, NodeTrace, ChatMessage,
)


# ── Intent Router ─────────────────────────────────────────────────

class RoutingInput(BaseModel):
    user_query: str
    history: list[ChatMessage] = []

class RoutingOutput(BaseModel):
    intent: str                   # "search"|"recommend"|"order"|"ops"|"chat"
    confidence: float             # [0, 1]
    routing_method: str           # "fast" | "slow"


# ── Search Node ───────────────────────────────────────────────────

class SearchNodeInput(BaseModel):
    query: str
    top_k: int = 10
    user_id: int | None = None
    user_memory: UserMemory | None = None

class SearchNodeOutput(BaseModel):
    products: list[ProductRef]
    docs: list[DocRef]
    latency_ms: int = 0

    # side_effect: FAISS query, SQL keyword lookup, embedding cache write


# ── Order Node ────────────────────────────────────────────────────

class OrderNodeInput(BaseModel):
    action: str                    # "status" | "cancel" | "refund" | "detail"
    order_id: int | None = None
    user_id: int | None = None

class OrderNodeOutput(BaseModel):
    result: dict[str, Any]         # {"status": ..., "order_no": ..., ...}
    status: str                    # "ok" | "error"

    # side_effect: deterministic — no LLM call, no API call beyond DB


# ── Analytics Node ─────────────────────────────────────────────────

class AnalyticsNodeInput(BaseModel):
    days: int = 7
    user_id: int | None = None

class AnalyticsNodeOutput(BaseModel):
    report_markdown: str = ""
    stats: dict[str, Any] = {}

    # side_effect: SQL aggregation + optional LLM summary


# ── Chat Node ─────────────────────────────────────────────────────

class ChatNodeInput(BaseModel):
    user_query: str
    history: list[ChatMessage] = []
    user_memory: UserMemory | None = None
    model_name: str = ""

class ChatNodeOutput(BaseModel):
    response: str

    # side_effect: LLM call, trace write


# ── Response Node ─────────────────────────────────────────────────

class ResponseNodeInput(BaseModel):
    final_response: str = ""
    ranked_items: list[RankedItem] = []
    error: str | None = None

class ResponseNodeOutput(BaseModel):
    formatted_response: str        # final user-facing text/markdown


# ── Eval Hook type ────────────────────────────────────────────────

EvalHook = Callable[[Any, Any], dict[str, float]]
# eval_func(node_output, ground_truth) → {"recall@10": 0.85, ...}
