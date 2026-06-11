"""
Routing — intent classification and pre-execution gating.

Pipeline:
  affinity.check()    → fast-path routing (structured, workflow, block affinity)
  classifier.classify() → L0+L1+signal fusion → FinalDecision
  grounding_gate.check() → executability gate → clarify or proceed

Entry point: classify(ctx) — called by orchestrator.
"""

from .affinity import try_route as _affinity_check
from .classifier import classify as _classify
from .grounding_gate import check as _grounding_check
from ..pipeline import PipelineContext


def classify(ctx: PipelineContext) -> dict | None:
    """Run all routing layers.

    Returns a terminal response dict if a layer produces a final answer
    (structured query hit, workflow dispatch, clarify reply), or None
    to continue to execution stage.

    When returning None, ctx.final_route is guaranteed to be set.
    """
    # Layer 1: Fast-path routing (may return terminal response)
    output = _affinity_check(ctx)
    if output is not None:
        return output

    # Layer 2: Intent classification (writes ctx.final_route)
    _classify(ctx)

    # Layer 3: Grounding gate (may return clarify reply)
    output = _grounding_check(ctx)
    if output is not None:
        return output

    return None
