"""
Intent Classifier — L0 + L1 + signal fusion + FinalDecision.

Pipeline:
  1. Dialogue context merge (multi-turn follow-up handling)
  2. L0 state_router — deterministic keyword routing
  3. L1 commerce_intent — LLM-based fine-grained classification
  4. Conversation signal fusion — confidence adjustment
  5. FinalDecision — single truth source: RouteDecision

This is the ONLY place intent classification happens.
entry_router is a pure dispatcher — it never classifies.
"""

from __future__ import annotations

import logging

from ..pipeline import PipelineContext
from ..state_router import RouteDecision
from ..contracts.search_plan import normalize_query

logger = logging.getLogger(__name__)

_COMMERCE_CONFIDENCE_THRESHOLD = 0.25  # below → route to chat

_SIGNAL_DELTA: dict[str, tuple[float, float]] = {
    "capability":        (-1.00, -0.10),
    "stop":              (-0.70, -0.70),
    "ack":               (-0.40, -0.40),
    "negative_feedback": (-0.30, -0.20),
}


def classify(ctx: PipelineContext) -> None:
    """Run full intent classification pipeline.

    Writes results to ctx:
      - ctx.commerce_result  (IntentResult or None)
      - ctx.final_route      (RouteDecision)
      - ctx.conv_state       (ConversationState or None)
      - ctx.query may be mutated by dialogue merge
    """
    from ..session_memory import get_conv_state

    conv_state = get_conv_state(ctx.session_id) if ctx.session_id else None

    # ── 1. Dialogue context merge ──
    _dialogue_merge(ctx, conv_state)

    # ── 2. L0 state_router ──
    from ..state_router import route as state_router
    route = state_router(ctx.query, conv_state)

    # Apply resolved query if context was filled
    if route.resolved_query and route.resolved_query != ctx.query:
        ctx.query = route.resolved_query
        ctx.state.user_query = ctx.query
        ctx.state.normalized_query = normalize_query(ctx.query)

    ctx.state.control_context.update(route.control_context)

    # ── 3. L1 commerce_intent (only when needed) ──
    commerce_result = None
    if route.needs_commerce_layer:
        from ..commerce_intent import classify as classify_commerce
        commerce_result = classify_commerce(ctx.query)

        # ── 4. Signal fusion ──
        from ..nodes.input_guard import detect_conversation_signals
        conv_signals = detect_conversation_signals(ctx.query)
        ctx.state.parallel_results["_conversation_signals"] = conv_signals.to_dict()
        if conv_signals.any_signal():
            intent_score = apply_signals(commerce_result, conv_signals)
            ctx.state.parallel_results["_intent_score"] = intent_score.to_dict()
            commerce_result.confidence = intent_score.adjusted_confidence

    # ── 5. FinalDecision ──
    ctx.commerce_result = commerce_result
    ctx.conv_state = conv_state
    ctx.final_route = _build_final_route(route, commerce_result)


# ── Dialogue merge ──────────────────────────────────────────────


def _dialogue_merge(ctx: PipelineContext, conv_state) -> None:
    """Merge follow-up input with previous query when system left a gap."""
    from ..state_router import has_strong_intent

    if not conv_state or not conv_state.dialogue.expects_followup:
        return

    # ── 1. Reference resolution (BEFORE intent check) ──
    ref = _try_resolve(ctx, conv_state)
    if ref is not None:
        conv_state.dialogue.expects_followup = False
        ctx.state.parallel_results["_resolved_ref"] = ref
        return

    # ── 2. Clarification follow-up ──
    if hasattr(conv_state, 'pending_reference') and conv_state.pending_reference is not None:
        pending = conv_state.pending_reference
        action = _infer_action_from_clarification_reply(ctx.query)
        if action is not None:
            from .reference_resolver import (
                ResolvedReference, ReferenceTarget, ReferenceAction,
                ClarificationReason, capability_for,
            )
            cap = capability_for(action)
            resolved = ResolvedReference(
                target=ReferenceTarget(product_ids=[pending.product_id]),
                product_name=pending.product_name,
                confidence=0.9,
                action=action,
                capability=cap,
            )
            conv_state.pending_reference = None
            conv_state.dialogue.expects_followup = False
            ctx.state.parallel_results["_resolved_ref"] = resolved
            return
        # User said something unrelated → clear pending, fall through
        conv_state.pending_reference = None

    # ── 3. Fall back to existing logic ──
    if has_strong_intent(ctx.query):
        conv_state.dialogue.expects_followup = False
    elif _is_ambiguous(ctx.query):
        conv_state.dialogue.expects_followup = False
        ctx.query = f"{conv_state.dialogue.last_user_query} {ctx.query}"
        conv_state.dialogue.injected_slot = ctx.query
    else:
        ctx.query = f"{conv_state.dialogue.last_user_query} {ctx.query}"
        conv_state.dialogue.injected_slot = ctx.query
        conv_state.dialogue.expects_followup = False


def _is_ambiguous(query: str) -> bool:
    """Deprecated — reference resolution now handled by reference_resolver.
    Kept for backward compatibility. Will be removed in next PR."""
    from .reference_resolver import resolve_reference, ReferenceContext
    ref = resolve_reference(query, ReferenceContext())
    return ref.product_id is not None or ref.action is not None


def _try_resolve(ctx: PipelineContext, conv_state) -> "ResolvedReference | None":
    """Try to resolve a product reference. Returns None if no reference."""
    from .reference_resolver import (
        resolve_reference, ReferenceContext, ProductReference,
    )
    from .affinity import build_action_context

    # Build ReferenceContext from affinity (reads product_card blocks from DB)
    actx = build_action_context(ctx.session_id) if ctx.session_id else None
    products: list[ProductReference] = []
    if actx:
        for block in actx.active_blocks:
            if block.type == "product_card":
                for p in block.data.get("products", []):
                    pid = p.get("product_id", p.get("id", 0))
                    pname = p.get("product_name", p.get("name", ""))
                    products.append(ProductReference(product_id=pid, product_name=pname))
                break

    ref_ctx = ReferenceContext(
        products=products,
        last_query=conv_state.dialogue.last_user_query if conv_state else "",
    )

    resolved = resolve_reference(ctx.query, ref_ctx)
    if resolved.product_id is None and resolved.action is None:
        return None  # No reference detected
    return resolved


def _infer_action_from_clarification_reply(query: str) -> "ReferenceAction | None":
    """从用户对澄清的回复中推断 action。只处理明确的关键词。"""
    q = query.strip()
    if any(kw in q for kw in ["购买", "下单", "买", "立即购买"]):
        from .reference_resolver import ReferenceAction
        return ReferenceAction.PURCHASE
    if any(kw in q for kw in ["加入购物车", "加购", "加购物车"]):
        from .reference_resolver import ReferenceAction
        return ReferenceAction.ADD_TO_CART
    if any(kw in q for kw in ["查看", "看看", "详情", "介绍"]):
        from .reference_resolver import ReferenceAction
        return ReferenceAction.VIEW_DETAIL
    return None


# ── Signal fusion ───────────────────────────────────────────────


def apply_signals(commerce_result, signals) -> "IntentScore":
    """Fuse conversation signals into commerce confidence.

    NOTE: mutates commerce_result.confidence as a side effect.
    Callers (classify()) depend on this — the mutated value flows
    into FinalDecision via ctx.commerce_result.
    """
    from ..nodes.input_guard import (
        IntentScore, ScoreAdjustment, ConversationSignals, _has_product_signal,
    )

    base = commerce_result.confidence if commerce_result else 0.0
    intent = commerce_result.intent if commerce_result else "chat"

    query = getattr(commerce_result, '_query', '') if commerce_result else ''
    has_product = _has_product_signal(query) if query else False

    adjustments: list[ScoreAdjustment] = []
    adjusted = base

    for name, (delta_no_product, delta_with_product) in _SIGNAL_DELTA.items():
        strength = getattr(signals, name, 0)
        if strength > 0:
            delta = delta_with_product if has_product else delta_no_product
            delta *= strength
            adjusted += delta
            adjustments.append(ScoreAdjustment(
                signal=f"{name}({strength})",
                delta=round(delta, 3),
            ))

    adjusted = max(0.0, min(1.0, adjusted))
    if adjusted < _COMMERCE_CONFIDENCE_THRESHOLD:
        adjusted = 0.0

    return IntentScore(
        intent=intent,
        base_confidence=round(base, 3),
        adjusted_confidence=round(adjusted, 3),
        adjustments=adjustments,
    )


# ── FinalDecision ───────────────────────────────────────────────


def _build_final_route(l0_route, l1_result=None) -> RouteDecision:
    """Single truth source from L0 + L1 + signals."""
    if l1_result is None:
        return l0_route

    if l1_result.confidence <= 0.0:
        return RouteDecision(
            intent="chat",
            confidence=0.6,
            reason="FinalDecision: signal override → chat",
            needs_commerce_layer=False,
            execution_hint="llm_direct",
            control_context=l0_route.control_context,
        )

    return RouteDecision(
        intent="commerce",
        confidence=l1_result.confidence,
        reason=f"FinalDecision: {l1_result.intent}({l1_result.confidence:.2f})",
        needs_commerce_layer=True,
        execution_hint=l0_route.execution_hint,
        control_context=l0_route.control_context,
    )
