"""
Chat Node — general-purpose LLM conversation (no RAG).

I/O Contract:
  Input:  ChatNodeInput  (user_query, history, user_memory, model_name)
  Output: ChatNodeOutput (response)
  side_effect: LLM call, trace write
"""
from ..state import AgentState, NodeTrace, ChatMessage
from ..contracts import ChatNodeInput, ChatNodeOutput
from ..cost_router import CostRouter, estimate_tokens

import time


def chat_node(state: AgentState) -> AgentState:
    """General chat: direct LLM response, no retrieval."""
    start = time.time()

    # Select model per-node
    model = CostRouter().select("chat", estimate_tokens(state))

    # Build messages from history
    from agents.core.llm_client import get_llm_client
    client = get_llm_client()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]
    for h in state.history[-10:]:   # last 10 turns
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": state.user_query})

    # Inject memory context if available
    if state.user_memory and state.user_memory.preferences:
        pref_str = ", ".join(
            f"{k}: {v:.2f}" for k, v in
            sorted(state.user_memory.preferences.items(), key=lambda x: x[1], reverse=True)[:5]
        )
        messages.insert(1, {"role": "system",
                            "content": f"用户偏好: {pref_str}"})

    # Build single prompt from messages
    prompt = _build_prompt(messages, model)

    response = client.chat(prompt, max_tokens=800)

    latency = int((time.time() - start) * 1000)

    # Trace
    state.trace.append(NodeTrace(
        node_name="chat",
        model_name=model,
        prompt_tokens=response.tokens_used,
        completion_tokens=0,
        latency_ms=latency,
    ))

    state.final_response = response.text
    state.ui_message = ""
    state.steps_done.append("chat")
    state.current_node = "chat"
    return state


def _build_prompt(messages: list[dict[str, str]], model: str = "") -> str:
    """Build a single prompt string from message list."""
    parts: list[str] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    parts.append("Assistant:")
    return "\n\n".join(parts)


_SYSTEM_PROMPT = """你是 ShopEase 的 AI 购物助手。

## 你可以帮助用户：
- 搜索和推荐商品
- 查询订单状态
- 发起退款或取消订单
- 回答平台相关问题

## 限制（必须遵守）：
- 你不能联系人工客服，也不能承诺"稍后联系""已经转接""已通知商家"
- 如果用户需要人工帮助，建议其查看商品页面的商家联系方式
- 不要编造不存在的服务能力（如"仓库正在打包""优惠券已发放""退款已到账"等）
- 退款、取消等操作需要用户显式确认后才能执行

请用简洁、专业的语气回答。回答不超过 200 字。"""
