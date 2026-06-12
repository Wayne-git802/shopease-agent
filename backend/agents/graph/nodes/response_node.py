"""
Response Node — format final output for the user.

I/O Contract:
  Input:  ResponseNodeInput  (final_response, ranked_items, error)
  Output: ResponseNodeOutput (formatted_response)
  side_effect: LLM explanation (best-effort, non-blocking)
"""
from ..state import AgentState
import logging

logger = logging.getLogger(__name__)


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
        # slot_def not found — skip to next missing field or fall through
        state.missing_fields.pop(0)

    elif state.ranked_items or state.tool_results.get("products"):
        # Branch 2: EXPLAIN + PRODUCT — recommendations with rationale
        products = state.tool_results.get("products", [])
        count = len(state.ranked_items) or len(products)
        parts = [state.final_response or f"为您找到 {count} 款商品："]
        all_reasons: set[str] = set()
        for item in state.ranked_items[:5]:
            all_reasons.update(item.reasons)
        if all_reasons:
            parts.append(f"\n💡 推荐理由: {', '.join(sorted(all_reasons)[:5])}")

        # ── LLM explanation (best-effort, non-blocking) ──
        score_breakdown = state.parallel_results.get("_score_breakdown", [])
        if products and score_breakdown:
            try:
                explanation = _generate_explanation(
                    state.user_query or "",
                    products[:3],
                    score_breakdown[:3],
                )
                if explanation:
                    state.parallel_results["_llm_explanation"] = explanation
                    parts.append(f"\n💡 {explanation}")
            except Exception:
                logger.debug("LLM explanation generation failed (non-critical)", exc_info=True)

        state.final_response = "\n".join(parts)
        state.ui_message = f"为你找到 {count} 款相关商品"
        state.current_node = "response"
        state.steps_done.append("response")
        return state

    elif state.parallel_results.get("_no_results"):
        # Branch 2.5: NO RESULTS — constraint relaxation failed
        state.final_response = "没有找到相关商品，请尝试其他关键词"
        state.ui_message = state.final_response
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


def _generate_explanation(query: str, products: list[dict],
                          score_breakdown: list[dict]) -> str | None:
    """Generate a one-sentence LLM explanation for the top results."""
    from agents.core.llm_client import get_llm_client

    top_products = []
    for i, p in enumerate(products):
        sb = score_breakdown[i] if i < len(score_breakdown) else {}
        comps = sb.get("components", {})
        top_products.append(
            f"{i+1}. {p.get('product_name', p.get('name', ''))}"
            f" | ¥{p.get('price', '?')} | 评分{p.get('rating', '?')}"
            f" | 语义匹配:{comps.get('product_embedding', 0.0):.2f}"
            f" | 价格契合:{comps.get('price_fit', 0.0):.2f}"
            f" | 好评度:{comps.get('sentiment', 0.0):.2f}"
        )

    prompt = f"""用户搜索: {query}
推荐商品:
{chr(10).join(top_products)}

请用一句话总结为什么推荐这些商品，突出与用户搜索最相关的特点。不要超过50字。"""

    client = get_llm_client()
    resp = client.chat(prompt, max_tokens=80)
    if resp and resp.text:
        return resp.text.strip()
    return None
