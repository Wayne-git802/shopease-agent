"""
Response Node — format final output for the user.

I/O Contract:
  Input:  ResponseNodeInput  (final_response, ranked_items, error)
  Output: ResponseNodeOutput (formatted_response)
  side_effect: none (pure formatting)
"""
from ..state import AgentState


def response_node(state: AgentState) -> AgentState:
    """Format final response. If error exists, return error message.

    P3: 3-way UI decision — clarify / explain+products / plain text.
    """
    from ..contracts.product_domain import SLOT_BY_KEY, MAX_CLARIFY_ROUNDS

    if state.error:
        state.final_response = f"抱歉，系统遇到了一些问题：{state.error}\n请稍后重试或联系客服。"
        state.current_node = "response"
        state.steps_done.append("response")
        return state

    # ── P3: 3-way UI decision ──

    if state.missing_fields and state.clarify_round < MAX_CLARIFY_ROUNDS:
        # Branch 1: CLARIFY — ask a question
        first_missing = state.missing_fields[0]
        slot_def = SLOT_BY_KEY.get(first_missing)
        if slot_def:
            state.final_response = slot_def.question
            state.current_node = "response"
            state.steps_done.append("response")
            state.ui_message = f"需要确认: {slot_def.label}"
            state.tool_results["_clarify"] = {
                "slot_key": slot_def.key,
                "question": slot_def.question,
                "options": slot_def.options,
            }
        return state

    elif state.ranked_items:
        # Branch 2: EXPLAIN + PRODUCT — recommendations with rationale
        parts = [state.final_response or f"为您找到 {len(state.ranked_items)} 款商品："]
        all_reasons: set[str] = set()
        for item in state.ranked_items[:5]:
            all_reasons.update(item.reasons)
        if all_reasons:
            parts.append(f"\n💡 推荐理由: {', '.join(sorted(all_reasons)[:5])}")
        state.final_response = "\n".join(parts)
        state.ui_message = f"为你找到 {len(state.ranked_items)} 款相关商品"
        state.current_node = "response"
        state.steps_done.append("response")
        return state

    else:
        # Branch 3: PLAIN TEXT — chat/analytics response
        if not state.final_response:
            state.final_response = "请问有什么可以帮您的？"
        state.current_node = "response"
        state.steps_done.append("response")
        return state
