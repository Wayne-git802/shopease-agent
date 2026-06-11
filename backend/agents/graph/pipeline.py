"""
Pipeline — core data structures for the LangGraph orchestration pipeline.

These types define the contract between orchestration stages and lay the
groundwork for future Agent Runtime evolution:

  Pipeline Runtime (Phase 3)
    → Agent Runtime (Phase 4, when agents natively return AgentResult)
    → MCP Tool Layer (Phase 5)
    → A2A (Phase 6)

Design rules:
  - PipelineContext is the single context object flowing through all stages.
  - Handoff is a first-class signal, not a dict flag.
  - AgentExecutor is a Protocol — executors are discovered via registry,
    not hardcoded if/elif chains.
  - AgentResult is the standard return type every executor eventually adopts.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════
# AgentCapability — typed capability tag for agent dispatch
# ═══════════════════════════════════════════════════════════════


class AgentCapability(StrEnum):
    """Semantic capability tag for the execution registry.

    StrEnum is intentionally both a str and an enum — backward-compatible
    with existing string comparisons.  CONVENTION: only the affinity layer
    (routing/affinity.py) may compare AgentCapability with raw strings.
    All other code MUST use enum members directly.

    Extension points (future):
      - is_core() distinguishes built-in agents from plugins
      - metadata dict for per-capability config (aliases, description)
    """
    ORDER = "order"
    CART = "cart"
    PURCHASE = "purchase"

    def is_core(self) -> bool:
        """True for built-in agents that are always registered."""
        return self in {AgentCapability.ORDER, AgentCapability.CART, AgentCapability.PURCHASE}


# ═══════════════════════════════════════════════════════════════
# Handoff — first-class agent handoff signal
# ═══════════════════════════════════════════════════════════════


@dataclass
class Handoff:
    """Explicit handoff from one agent to another.

    Replaces the old pattern of stuffing {"_handoff": "purchase"} into
    a return dict.  The handoff loop in execution/__init__.py reads this
    and re-enters the executor registry with the target agent.
    """

    target: AgentCapability
    payload: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# AgentResult — single status, all executors return this
# ═══════════════════════════════════════════════════════════════


@dataclass
class AgentResult:
    """Every AgentExecutor returns exactly this.

    The dispatcher switches on `status` only — never inspects
    internal fields.  Adding a new agent type requires zero
    changes to the dispatcher.

    Phase 4: agents natively return AgentResult.
    Phase 5: capability typed via AgentCapability.
    """

    status: str  # "success" | "fallback" | "handoff" | "error"

    response: dict | None = None   # set when status == "success"
    handoff: Handoff | None = None # set when status == "handoff"
    metadata: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# AgentExecutor Protocol — what every executor must implement
# ═══════════════════════════════════════════════════════════════


@runtime_checkable
class AgentExecutor(Protocol):
    """Protocol for any executable agent in the system.

    Phase 4: agents implement this natively.
    Phase 5: name → capability (AgentCapability enum).
    Phase 6: execute receives AgentContext (memory + input), can_handle
             still receives PipelineContext (needs commerce_result for routing).
    """

    capability: AgentCapability
    priority: int = 0

    def can_handle(self, ctx: "PipelineContext") -> bool:
        """Return True if this executor should handle the current context.
        Uses PipelineContext — needs commerce_result.intent for routing.
        """
        ...

    def execute(self, ctx: "AgentContext") -> AgentResult:
        """Execute and return a standardized result.
        Uses AgentContext — agent only needs memory + input.
        """
        ...


# ═══════════════════════════════════════════════════════════════
# AgentContext — standard input for every agent's execute()
# ═══════════════════════════════════════════════════════════════


@dataclass
class AgentContext:
    """Standard input passed to every agent during execute().

    Carries only what agents need: query, user info, and memory.
    Does NOT carry routing data (commerce_result, final_route) —
    those live on PipelineContext and are consumed by the dispatcher.
    """

    query: str
    user_id: int | None
    session_id: str
    display_id: str = ""
    memory: "AgentMemory" = field(default_factory=lambda: _new_agent_memory())

    @classmethod
    def from_pipeline(cls, ctx: "PipelineContext") -> "AgentContext":
        from agents.graph.memory import AgentMemory
        return cls(
            query=ctx.query,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            display_id=ctx.display_id,
            memory=AgentMemory(),
        )


def _new_agent_memory():
    """Lazy import helper — avoids circular dependency at module level."""
    from agents.graph.memory import AgentMemory
    return AgentMemory()


# ═══════════════════════════════════════════════════════════════
# PipelineContext — single context through all stages
# ═══════════════════════════════════════════════════════════════


@dataclass
class PipelineContext:
    """Single context object flowing through routing → execution → response.

    Future: when agents become independent runtime entities, this evolves
    into a TaskContext with the same shape.
    """

    # ── Input (immutable per request) ──
    query: str
    user_id: int | None = None
    session_id: str = ""
    query_type: str = ""
    product_id: str = ""
    display_id: str = ""
    history: list[dict] | None = None

    # ── Intermediate (each stage fills what it owns) ──
    state: Any = None                   # AgentState
    commerce_result: Any = None         # IntentResult from commerce_intent
    final_route: Any = None             # RouteDecision
    conv_state: Any = None              # ConversationState
    handoff: Handoff | None = None      # set by execution stage

    # ── Timing ──
    _start: float = 0.0

    def elapsed_ms(self) -> int:
        """Milliseconds since pipeline start. Replaces 9× repeated pattern."""
        return int((_time.time() - self._start) * 1000)


# ═══════════════════════════════════════════════════════════════
# UnrecoverableError — pipeline exhausted without response
# ═══════════════════════════════════════════════════════════════


class UnrecoverableError(Exception):
    """Pipeline exhausted all stages without producing a response."""
