"""
Execution — dispatcher that routes to the right executor.

Architecture:
  - Domain executors (Order, Cart, Purchase) register into _registry.
  - GraphExecutor is NOT registered — it is the default fallback.
  - dispatch(target) is used for explicit handoffs (Cart → Purchase).
  - resolve(ctx) does intent-based can_handle matching.
  - run(ctx) is the main entry point, with a handoff loop.
"""

from __future__ import annotations

import logging

from ..pipeline import PipelineContext, AgentContext, AgentResult, AgentCapability, Handoff

logger = logging.getLogger(__name__)

# capability → AgentExecutor
_registry: dict[AgentCapability, "AgentExecutor"] = {}

# Imported here to avoid circular dependency
from ..pipeline import AgentExecutor


def register(executor: AgentExecutor) -> None:
    """Register an executor. Raises TypeError if protocol not satisfied."""
    if not isinstance(executor, AgentExecutor):
        raise TypeError(f"{executor} does not satisfy AgentExecutor protocol")
    _registry[executor.capability] = executor
    logger.debug("Registered executor: %s (priority=%d)", executor.capability.value, executor.priority)


def dispatch(target: AgentCapability, agent_ctx: "AgentContext") -> AgentResult:
    """Explicit dispatch to a named executor. Used for handoffs."""
    executor = _registry.get(target)
    if executor is None:
        return AgentResult(
            status="error",
            response={"reply": f"No executor registered for target '{target.value}'"},
        )
    return executor.execute(agent_ctx)


def resolve(ctx: PipelineContext) -> AgentExecutor | None:
    """Intent-based resolution — first can_handle wins (sorted by priority)."""
    sorted_executors = sorted(
        _registry.values(),
        key=lambda e: e.priority,
        reverse=True,
    )
    for executor in sorted_executors:
        try:
            if executor.can_handle(ctx):
                return executor
        except Exception:
            logger.warning("Executor.can_handle failed for %s", executor.capability.value, exc_info=True)
    return None


def run(ctx: PipelineContext) -> AgentResult:
    """Main execution entry point. Runs the handoff loop.

    Returns:
      AgentResult with status="success" → proceed to response stage.
      AgentResult with status="error" → unrecoverable.
    """
    from .graph_executor import execute as graph_execute

    # Build once — same instance flows through handoff loop (shared cache)
    agent_ctx = AgentContext.from_pipeline(ctx)

    # ── Reference-based dispatch (runs BEFORE resolve) ──
    resolved_ref = ctx.state.parallel_results.get("_resolved_ref")
    if resolved_ref is not None:
        target = getattr(resolved_ref, 'target', None)
        if target and target.product_ids:
            agent_ctx.reference = target
        cap_str = getattr(resolved_ref, 'capability', None)
        if cap_str:
            # Resolve string capability → AgentCapability
            cap = _resolve_capability(cap_str)
            if cap:
                return dispatch(cap, agent_ctx)
        # No capability → fall through to existing resolve/graph

    while True:
        # Handoff takes priority
        if ctx.handoff:
            result = dispatch(ctx.handoff.target, agent_ctx)
            ctx.handoff = None
        else:
            executor = resolve(ctx)
            if executor is not None:
                result = executor.execute(agent_ctx)
            else:
                result = graph_execute(ctx)   # graph keeps PipelineContext

        # Status switch — dispatcher logic, no field inspection
        if result.status == "handoff":
            ctx.handoff = result.handoff
            continue
        if result.status == "fallback":
            result = graph_execute(ctx)       # graph keeps PipelineContext
            return result
        if result.status == "error":
            return result
        return result


# ── Register domain agents on import ──

from agents.order.agent import order_agent
from agents.cart.agent import cart_agent
from agents.purchase.agent import purchase_agent

register(order_agent)
register(cart_agent)
register(purchase_agent)


def _resolve_capability(cap_str: str) -> "AgentCapability | None":
    """Resolve string capability to AgentCapability enum."""
    for cap in AgentCapability:
        if cap.value == cap_str:
            return cap
    # Try matching by capability name (e.g., "order" might be AgentCapability.ORDER)
    try:
        return AgentCapability(cap_str)
    except ValueError:
        return None
