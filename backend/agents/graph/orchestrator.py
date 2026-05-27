"""
Orchestrator — single entry point for the LangGraph AI commerce system.

Usage:
    from agents.graph.orchestrator import run

    response = run(query="推荐一款手机", user_id=42)
"""
from .state import AgentState, ChatMessage, UserMemory, PurchaseSummary
from .memory import memory_manager
from .trace import persist_trace, RuntimeTrace, PhaseRecord, NODE_TO_PHASE, PHASE_LABELS
from .graph_builder import get_graph
from .fallback_graph import get_fallback_graph
from .session_memory import get as get_session_memory, put as put_session_memory, clear as clear_session_memory
from .session_memory import get_conv_state, put_conv_state, clear_conv_state
from .preprocessor import build_conversation_state
from .contracts.ui_state import (
    UIState, AIResponse, UIBlock, NODE_TO_UI_STATE, UI_STATE_MESSAGES
)
from .contracts.product_domain import SLOT_BY_KEY, MAX_CLARIFY_ROUNDS
from .contracts.search_plan import normalize_query
from datetime import datetime, timezone


class UnrecoverableError(Exception):
    """Graph failed and fallback also failed."""


def run(query: str, user_id: int | None = None,
        history: list[dict] | None = None,
        session_id: str = "",
        query_type: str = "",
        product_id: str = "") -> dict:
    """Run the full LangGraph pipeline and return structured data.

    Returns a dict with: reply, intent, confidence, ranked_items, tool_results.

    Flow:
      1. Build initial state
      2. Enrich with long-term memory
      3. Set query_type hint for entry_router
      4. Invoke main graph (entry_router handles routing internally)
      5. On failure → invoke fallback graph
      6. Persist trace + update memory
    """
    import time as _time
    _start = _time.time()
    # ── 1. Build state ──
    history_msgs = []
    if history:
        history_msgs = [
            ChatMessage(role=h.get("role", "user"), content=h.get("content", ""))
            for h in history[-10:]
        ]

    state = AgentState(
        user_query=query,
        user_id=user_id,
        session_id=session_id or "",
        history=history_msgs,
        normalized_query=normalize_query(query),
    )

    # ── 2. Memory enrichment — DEFERRED to after Input Guard ──
    # Memory is expensive (4-6 DB queries). Only build it when we know
    # the query is search/recommend, not plain chat.
    _user_id_for_memory = user_id

    # ── 3. Set query_type hint ──
    state.parallel_results["query_type"] = query_type

    # Map query_type to recommend_type for recommend_node
    if query_type in ("popular", "for-you", "trending", "similar"):
        state.parallel_results["recommend_type"] = query_type

    # Pass product_id for similar-product recommendations
    if product_id:
        state.parallel_results["similar_product_id"] = product_id

    # ── 1. State Router — Single Routing Authority ──
    # Replaces Preprocessor + Input Guard. One decision point.
    # Trivial path: template reply (0 LLM). Lightweight: chat_node only.
    # Full graph: ConstraintParser → Memory → Graph.
    _original_query = query   # saved for conversation state

    # ── 0.5 Active OrderWorkflow check ──
    # If the user is mid-order-workflow, short-circuit to OrderAgent.
    # Handles context-dependent queries like "第一个" / "确认" / "算了"
    # that state_router would misclassify as greeting/chat/unclear.
    if session_id:
        from agents.order.workflow_store import load as load_owf
        owf = load_owf(session_id)
        if owf and owf.current_step != "idle":
            from agents.order.agent import run as run_order_agent
            result = run_order_agent(query=query, user_id=user_id, session_id=session_id)
            if not result.get("_fallback"):
                result["session_id"] = session_id
                result["query_type"] = query_type
                result["runtime"] = {"total_ms": int((_time.time() - _start) * 1000)}
                return result

        # PurchaseAgent shortcut: if last assistant msg was a purchase confirm prompt
        from agents.purchase.agent import _get_recent_blocks
        blocks = _get_recent_blocks(session_id, block_type="confirm_dialog")
        for b in blocks:
            if b.get("type") == "confirm_dialog" and b.get("data", {}).get("action") == "purchase":
                from agents.purchase.agent import run as run_purchase_agent
                result = run_purchase_agent(query=query, user_id=user_id, session_id=session_id)
                if not result.get("_fallback"):
                    result["session_id"] = session_id
                    result["query_type"] = query_type
                    result["runtime"] = {"total_ms": int((_time.time() - _start) * 1000)}
                    return result
                break

    from .state_router import route as state_router, _pick_template

    conv_state = get_conv_state(session_id) if session_id else None
    route = state_router(query, conv_state)

    # Apply resolved query if context was filled
    if route.resolved_query and route.resolved_query != query:
        query = route.resolved_query
        state.user_query = query
        state.normalized_query = normalize_query(query)

    state.control_context = route.control_context

    # ── 2. Commerce Layer (only when needed) ──
    commerce_result = None
    if route.needs_commerce_layer:
        from .commerce_intent import classify as classify_commerce
        commerce_result = classify_commerce(query)

    # ── 2.5 OrderAgent routing ──
    if commerce_result and commerce_result.intent == "order":
        from agents.order.agent import run as run_order_agent
        result = run_order_agent(query=query, user_id=user_id, session_id=session_id)
        result["session_id"] = session_id
        result["query_type"] = query_type
        result["runtime"] = {"total_ms": int((_time.time() - _start) * 1000)}
        return result

    # ── 2.6 PurchaseAgent routing ──
    if commerce_result and commerce_result.intent == "purchase" and commerce_result.confidence >= 0.3:
        from agents.purchase.agent import run as run_purchase_agent
        result = run_purchase_agent(query=query, user_id=user_id, session_id=session_id)
        if not result.get("_fallback"):
            result["session_id"] = session_id
            result["query_type"] = query_type
            result["runtime"] = {"total_ms": int((_time.time() - _start) * 1000)}
            return result

    # ── 3. Response Policy — resource scheduler ──
    from .response_policy import plan as policy_plan
    plan = policy_plan(route, commerce_result)

    # ── Template path ──
    if plan.execution_mode == "template":
        reply = _pick_template(route.intent)
        return {
            "reply": reply, "intent": route.intent,
            "confidence": route.confidence, "ui_state": "done",
            "message": route.reason, "blocks": [],
            "ranked_items": [], "tool_results": {},
            "session_id": session_id, "query_type": query_type,
            "runtime": {"phases": [{"phase": "routing", "label": "快速路由", "status": "ok", "ms": int((_time.time() - _start) * 1000)}], "total_ms": int((_time.time() - _start) * 1000)},
            "explain": None, "retrieval": None,
            "show_budget_hint": False, "show_clarify_hint": False,
        }

    # ── LLM direct path: single LLM call, no memory, no graph ──
    if plan.execution_mode == "llm_direct":
        from .nodes.chat_node import chat_node
        state.user_memory = None
        state = chat_node(state)
        response = AIResponse(
            ui_state=UIState.DONE, message=route.reason,
            confidence=route.confidence, blocks=[],
            reply=state.final_response, intent=route.intent,
        )
        result = response.model_dump()
        result.update(runtime={"phases": [{"phase": "routing", "label": "LLM直出", "status": "ok", "ms": int((_time.time() - _start) * 1000)}], "total_ms": int((_time.time() - _start) * 1000)}, explain=None, retrieval=None,
                      show_budget_hint=False, show_clarify_hint=False,
                      session_id=session_id, query_type=query_type,
                      ranked_items=[], tool_results={})
        return result

    # ── Graph path: memory → ConstraintParser → full_graph ──

    # ── 4. Memory Hydration (per plan, with per-request cache) ──
    if _user_id_for_memory and plan.memory != "none":
        try:
            from .memory import load_preferences, load_purchase_profile
            # Per-request cache on state — traceable, no cross-request leak
            cache = getattr(state, '_memory_cache', None) or {}
            uid = _user_id_for_memory

            if plan.memory == "preferences":
                if "prefs" not in cache:
                    cache["prefs"] = load_preferences(uid)
                state.user_memory = UserMemory(
                    user_id=uid, preferences=cache["prefs"],
                    purchase_summary=PurchaseSummary(),
                )
            elif plan.memory == "purchase":
                if "purchase" not in cache:
                    cache["purchase"] = load_purchase_profile(uid)
                state.user_memory = UserMemory(
                    user_id=uid, preferences={},
                    purchase_summary=cache["purchase"],
                )
            else:  # full
                state.user_memory = memory_manager.build(uid)

            state._memory_cache = cache
        except Exception:
            pass

    # ── Pass state_router intent to entry_router via control_context ──
    # entry_router is an EXECUTOR — accepts preset for definitive intents.
    # "commerce" is deliberately excluded: entry_router + ConstraintParser own the fine-grained split.
    if route.intent not in ("commerce", "unclear"):
        state.control_context["preset_intent"] = route.intent

    # ── 3.2 ConstraintParser: unified query classification ──
    # Single entry point replacing scattered sort/intent detection.
    # Produces a SearchPlan v2 consumed by all downstream nodes.
    from .nodes.constraint_parser import parse as parse_constraints
    from .contracts.search_plan import QueryIntent
    plan = parse_constraints(query)
    state.parallel_results["_search_plan"] = plan.to_dict()
    if plan.is_structured():
        state.parallel_results["query_type"] = "search"
    elif plan.intent == QueryIntent.RECOMMEND:
        state.parallel_results["query_type"] = "recommend"
    # Ambiguous stays as-is — entry_router handles it
    # Pre-set search phase info for trace
    phase = plan.to_phase()
    state.parallel_results["_search_phase_detail"] = phase.get("detail", "")
    state.parallel_results["_search_phase_label"] = phase.get("label", "")
    # Store hint flags for UI
    state.parallel_results["_show_budget_hint"] = plan.show_budget_hint

    # ── 3.3 Execution Validator — plan stability gate ──
    # Validates SearchPlan before downstream nodes consume it.
    # Corrects: sort semantics mismatch, confidence gating, recommend_type drift.
    from .execution_validator import validate as validate_plan, get_validated_recommend_type
    from .decision_trace import DecisionTrace, BranchDecision, build_trace, snapshot_signals

    # Determine has_history for recommend_type validation
    _has_history = bool(
        _user_id_for_memory
        and state.user_memory
        and state.user_memory.purchase_summary
        and state.user_memory.purchase_summary.total_orders > 0
    )

    # Commerce confidence (from L1)
    _commerce_conf = commerce_result.confidence if commerce_result else 0.0

    # Current recommend_type (may be empty if not set by API)
    _current_rec_type = state.parallel_results.get("recommend_type", "")

    # Run validation
    validated = validate_plan(
        plan=plan,
        query=query,
        commerce_confidence=_commerce_conf,
        recommend_type=_current_rec_type,
        intent=route.intent,
        user_id=_user_id_for_memory,
        has_history=_has_history,
    )

    # Apply validated results
    state.parallel_results["_search_plan"] = validated.to_dict()
    if validated.downgraded:
        # Plan was downgraded — override query_type to remove "search" hint
        if state.parallel_results.get("query_type") == "search":
            state.parallel_results["query_type"] = "recommend"

    # Resolve and store validated recommend_type
    corrected_rec_type = get_validated_recommend_type(validated)
    state.parallel_results["recommend_type"] = corrected_rec_type

    # Store validation decisions for trace
    state.parallel_results["_validator_decisions"] = validated.to_dict()

    # ── 3.4 Decision Trace anchor ──
    # Initialize trace structure for this execution
    _dt = DecisionTrace(
        session_id=session_id,
        query=query,
        plan_version="v2",
        plan_raw=plan.to_dict(),
        plan_validated=validated.to_dict(),
        validation_decisions=[d.to_dict() for d in validated.decisions],
        plan_downgraded=validated.downgraded,
    )
    # Store on state for later enrichment
    state.parallel_results["_decision_trace"] = _dt
    state.parallel_results["_show_clarify_hint"] = plan.show_clarify_hint

    # ── 3.5 P3: Session memory restore ──
    # If the user is answering a previous clarify question, restore context.
    session_mem = get_session_memory(session_id)
    if session_mem and session_mem.pending_intent:
        # entry_router will see this via session_memory; but we also
        # collect the answer here so recommend_node has it.
        state.parallel_results["_clarify_answer"] = query
        state.parallel_results["_collected_slots"] = dict(session_mem.collected_slots)

    # ── 4. Invoke main graph ──
    main_graph = get_graph()
    fallback_graph = get_fallback_graph()

    try:
        result = main_graph.invoke(state)
        state = AgentState(**result) if isinstance(result, dict) else result
    except Exception as e:
        # Try fallback
        try:
            state.error = str(e)
            result = fallback_graph.invoke(state)
            state = AgentState(**result) if isinstance(result, dict) else result
        except Exception as e2:
            raise UnrecoverableError(f"Both graphs failed: main={e}, fallback={e2}")

    # ── 5. Persist trace + update memory ──
    try:
        persist_trace(state.trace)
    except Exception:
        pass

    if user_id:
        try:
            memory_manager.update(state)
        except Exception:
            pass

    # --- 6. Session memory lifecycle ---
    clarify_data = state.tool_results.get("_clarify")
    if clarify_data and session_id:
        # Graph wants to ask a question
        from .session_memory import SessionMemory
        sm = SessionMemory(
            session_id=session_id,
            pending_intent=state.intent,
            collected_slots=state.parallel_results.get("_collected_slots", {}),
            missing_slots=state.missing_fields,
        )
        put_session_memory(sm)

        # ConversationState for preprocessor
        cs = build_conversation_state(
            session_id=session_id,
            last_intent=state.intent,
            original_query=_original_query,
            clarify_data=clarify_data,
            ai_reply=state.final_response,
        )
        put_conv_state(cs)
    elif session_id:
        # No clarify — clear old session memory
        clear_session_memory(session_id)
        # Still write conversation state for continuity
        cs = build_conversation_state(
            session_id=session_id,
            last_intent=state.intent,
            original_query=_original_query,
            clarify_data=None,
            ai_reply=state.final_response,
        )
        put_conv_state(cs)

    # ── 6.5 Phase B-2: Persist clarify answers to memory distribution ──
    if user_id and session_mem and session_mem.pending_intent and not clarify_data:
        # User just completed a clarify round — persist collected slots
        collected = state.parallel_results.get("_collected_slots", {})
        if collected:
            try:
                from .feedback.memory_distribution import merge_preference
                for slot_key, slot_value in collected.items():
                    merge_preference(
                        key=slot_key,
                        new_value=str(slot_value),
                        user_id=user_id,
                        source="clarify",
                    )
            except Exception:
                pass  # memory persistence is non-critical

    # ── 7. Build AIResponse ──
    last_node = state.current_node or (state.steps_done[-1] if state.steps_done else "chat")
    ui_state = NODE_TO_UI_STATE.get(last_node, UIState.DONE)

    # Override: if clarify was requested, use CLARIFYING
    if clarify_data:
        ui_state = UIState.CLARIFYING

    message = state.ui_message or UI_STATE_MESSAGES.get(ui_state, "")

    # ── 7.5 Phase A: Runtime Trace (product cognition timeline) ──
    rt = RuntimeTrace()
    if state.trace:
        for t in state.trace:
            phase = NODE_TO_PHASE.get(t.node_name, "responding")
            label = PHASE_LABELS.get(phase, phase)
            detail = ""
            # Inject search strategy detail from SearchPlan
            if t.node_name == "search":
                plan_label = state.parallel_results.get("_search_phase_label", "")
                plan_detail = state.parallel_results.get("_search_phase_detail", "")
                if plan_label:
                    label = plan_label
                if plan_detail:
                    detail = plan_detail
            rt.phases.append(PhaseRecord(
                phase=phase,
                label=label,
                status="ok",
                ms=t.latency_ms,
                detail=detail,
            ))
        rt.total_ms = sum(t.latency_ms for t in state.trace)
    runtime_dict = rt.to_dict() if rt.phases else None

    # ── 7.6 Phase A: Explain factors ──
    explain_dict = None
    if state.ranked_items:
        factors = []
        seen = set()
        for item in state.ranked_items[:5]:
            for reason in (item.reasons or [])[:2]:
                if reason not in seen:
                    seen.add(reason)
                    factors.append({"label": reason})
                    if len(factors) >= 4:
                        break
            if len(factors) >= 4:
                break
        if factors:
            explain_dict = {"title": "为什么推荐这些？", "factors": factors}

    # ── 7.7 Phase A: Retrieval info ──
    retrieval_dict = None
    search_meta = state.tool_results.get("_search_meta")
    if search_meta:
        candidates = search_meta.get("candidates", 0)
        after_filter = search_meta.get("after_filter", 0)
        after_rank = search_meta.get("after_rank", 0)
        retrieval_dict = {
            "summary": "基于商品描述、评论和相似商品分析",
            "detail": f"{candidates} 候选 → {after_filter} 过滤 → {after_rank} 排序",
        }

    # Build blocks based on intent
    blocks: list[UIBlock] = []

    # P3: Clarify block takes priority
    if clarify_data:
        blocks.append(UIBlock(type="clarify", data={
            "slot_key": clarify_data.get("slot_key", ""),
            "question": clarify_data.get("question", ""),
            "options": clarify_data.get("options", []),
        }))

    # P3: Explain block — if recommendations have reasons
    if state.ranked_items:
        explained_items = []
        for item in state.ranked_items[:5]:
            if item.reasons:
                # Look up product name from tool_results
                name = str(item.id)
                for p in state.tool_results.get("products", []):
                    if p.get("product_id") == item.id or p.get("id") == item.id:
                        name = p.get("name", str(item.id))
                        break
                explained_items.append({"name": name, "reasons": item.reasons})
        if explained_items:
            blocks.append(UIBlock(type="explain", data={
                "summary": f"为什么推荐这 {len(explained_items)} 款商品？",
                "items": explained_items,
            }))

    # Product cards
    if state.intent in ("recommend", "search") and state.tool_results.get("products"):
        blocks.append(UIBlock(type="product_card", data={"products": state.tool_results["products"]}))
    elif state.intent in ("recommend", "search"):
        # Fallback: no products found — expand to popular items
        blocks.append(UIBlock(type="message", data={
            "text": "没有找到完全匹配的商品，以下是为您推荐的热门商品：",
            "level": "info"
        }))
        # Try popular as fallback
        try:
            from agents.commerce.engine import RecommendEngine
            engine = RecommendEngine()
            popular = engine.get_popular()
            if popular:
                blocks.append(UIBlock(type="product_card", data={"products": popular}))
        except Exception:
            pass
    elif state.intent == "analytics":
        blocks.append(UIBlock(type="report", data={"markdown": state.final_response}))
    elif state.tool_results.get("health"):
        h = state.tool_results["health"]
        blocks.append(UIBlock(type="metric", data={"status": h.get("status", "unknown")}))

    trace_summary = None
    if state.trace:
        last_trace = state.trace[-1]
        trace_summary = {
            "total_ms": sum(t.latency_ms for t in state.trace),
            "last_node": last_trace.node_name,
            "model": last_trace.model_name or "fast",
            "cache_hit": last_trace.cache_hit,
        }

    response = AIResponse(
        ui_state=ui_state,
        message=message,
        confidence=state.confidence,
        blocks=blocks,
        reply=state.final_response,
        intent=state.intent,
        trace=trace_summary,
        show_budget_hint=state.parallel_results.get("_show_budget_hint", False),
        show_clarify_hint=state.parallel_results.get("_show_clarify_hint", False),
    )

    result = response.model_dump()
    result["runtime"] = runtime_dict
    result["explain"] = explain_dict
    result["retrieval"] = retrieval_dict

    # ── Phase B-4: Persist SessionTrace ──
    try:
        from agents.models import SessionTrace

        # Build ranked snapshots for before/after comparison
        before = [
            {"id": p.id, "name": p.name, "price": p.price, "category": p.category}
            for p in state.retrieved_products[:10]
        ]
        after = [
            {"id": r.id, "name": "", "price": 0, "category": ""}
            for r in state.ranked_items[:10]
        ]
        # Enrich after with product data from tool_results
        products_raw = state.tool_results.get("products", [])
        prod_map = {p.get("product_id", 0): p for p in products_raw if isinstance(p, dict)}
        for i, r in enumerate(state.ranked_items[:10]):
            pdata = prod_map.get(r.id, {})
            after[i] = {
                "id": r.id,
                "name": pdata.get("product_name", pdata.get("name", "")),
                "price": float(pdata.get("price", 0)),
                "category": pdata.get("category_name", ""),
            }

        signals = {}
        cats = state.parallel_results.get("_feedback_categories", [])
        if cats:
            from .feedback.signal_store import get_user_signals
            if state.user_id:
                all_sigs = get_user_signals(state.user_id)
                signals = {cat: round(all_sigs.get(cat, 0), 3) for cat in cats if cat in all_sigs}

        # ── Build events list (Phase A: block-grouped observability events) ──
        events: list[dict] = []

        # Helper: find trace latency for a node name
        def _node_ms(name: str) -> int:
            for t in (state.trace or []):
                if t.node_name == name:
                    return t.latency_ms
            return 0

        # 1) Routing block
        events.append({
            "block": "routing",
            "type": "classify",
            "ms": _node_ms("entry_router"),
            "payload": {
                "intent": state.intent,
                "confidence": round(state.confidence, 3),
                "method": state.routing_method,
            },
        })

        # 2) Retrieval block
        search_meta = state.tool_results.get("_search_meta", {})
        search_plan = state.parallel_results.get("_search_plan", {})
        events.append({
            "block": "retrieval",
            "type": search_plan.get("strategy", "semantic"),
            "ms": _node_ms("search") or _node_ms("recommend"),
            "payload": {
                "strategy": search_plan.get("strategy", "semantic"),
                "sort_by": search_plan.get("sort_by"),
                "direction": search_plan.get("direction"),
                "candidates": search_meta.get("candidates", 0),
                "after_filter": search_meta.get("after_filter", 0),
                "after_rank": search_meta.get("after_rank", 0),
            },
        })

        # 3) Ranking block — with before/after changes
        ranking_changes: list[dict] = []
        if state.ranked_items:
            before_ids = [p.id for p in (state.retrieved_products or [])[:10]]
            for i, r in enumerate(state.ranked_items[:10]):
                if r.id in before_ids:
                    old_idx = before_ids.index(r.id)
                    delta = old_idx - i
                    if delta != 0:
                        ranking_changes.append({
                            "product_id": r.id,
                            "before": old_idx + 1,
                            "after": i + 1,
                            "delta": delta,
                        })
        signal_list: list[str] = [
            f"{k} {v:+.2f}" for k, v in signals.items()
        ] if signals else []
        events.append({
            "block": "ranking",
            "type": "rerank",
            "ms": _node_ms("merge"),
            "payload": {
                "before_count": len(state.retrieved_products or []),
                "after_count": len(state.ranked_items or []),
                "changes": ranking_changes,
                "signals": signal_list,
            },
        })

        # 4) Response block
        events.append({
            "block": "response",
            "type": "generate",
            "ms": _node_ms("generate") or _node_ms("chat"),
            "payload": {
                "length": len(state.final_response or ""),
                "has_reply": bool(state.final_response),
            },
        })

        # ── P1: Enrich DecisionTrace with strategy decisions ──
        _dt = state.parallel_results.get("_decision_trace")
        if isinstance(_dt, DecisionTrace):
            # ── Search strategy decision ──────────────────────
            _strategy_dec = state.parallel_results.get("_search_strategy_decision", {})
            _search_strategy = _strategy_dec.get("strategy", "semantic")

            # Count structured results for HYBRID
            _struct_count = len(
                state.parallel_results.get("_structured_products", [])
            )

            # Merge policy metadata
            _merged = state.parallel_results.get("_merge_policy", {})

            _dt.node_decisions = [
                BranchDecision(
                    node="search",
                    branch=_search_strategy,
                    reason=_strategy_dec.get("reason", ""),
                    inputs={
                        "strategy": _search_strategy,
                        "dual_source": _strategy_dec.get("dual_source", False),
                        "structured_count": _struct_count,
                        "semantic_count": len(state.retrieved_products or []),
                    },
                ),
                BranchDecision(
                    node="recommend",
                    branch=state.parallel_results.get("recommend_type", "popular"),
                    reason=f"intent={state.intent}, user_id={state.user_id}",
                    inputs={"intent": state.intent},
                ),
                BranchDecision(
                    node="merge",
                    branch="fusion_p1",
                    reason=(
                        f"policy={_merged.get('policy', 'default')}, "
                        f"sw={_merged.get('search_weight', 0.5)}, "
                        f"rw={_merged.get('rec_weight', 0.5)}, "
                        f"div={_merged.get('diversity_lambda', 0.25)}"
                    ),
                    inputs={
                        "search_count": len(state.retrieved_products or []),
                        "rec_count": len(state.ranked_items or []),
                        "struct_count": _struct_count,
                        "policy": state.parallel_results.get("_merge_policy", {}),
                    },
                ),
            ]

            # Capture signal snapshot
            _dt.signal_snapshot = snapshot_signals(state.user_id)
            _dt.recorded_at = datetime.now(timezone.utc).isoformat()

        # Serialize for persistence
        _dt_dict = _dt.to_dict() if isinstance(_dt, DecisionTrace) else {}
        # ──────────────────────────────────────────────────────

        SessionTrace.objects.create(
            session_id=session_id,
            user_id=state.user_id,
            query=query,
            intent=state.intent,
            routing_conf=state.confidence,
            ui_state=ui_state.value,
            reply=state.final_response[:500],
            phases=runtime_dict["phases"] if runtime_dict else [],
            events=events,
            ranked_before=before,
            ranked_after=after,
            signals_applied=signals,
            block_count=len(blocks),
            total_ms=runtime_dict["total_ms"] if runtime_dict else 0,
            decision_trace=_dt_dict,
        )
    except Exception as e:
        import traceback
        print(f"[orchestrator] SessionTrace write failed: {e}")
        traceback.print_exc()

    return result
