"""
Workflow Recovery — restore OrderAgent state after page refresh / reconnect.
"""

from __future__ import annotations

from .workflow_store import load as load_workflow
from .state_machine import OrderSessionState, OrderStep


def recover(session_id: str) -> dict:
    """
    Recover workflow state for a session.

    Returns:
        {"recovered": bool, "state": OrderSessionState|None, "message": str}
    """
    wf = load_workflow(session_id)
    if not wf:
        return {"recovered": False, "state": None, "message": "没有活跃的订单操作"}

    state = OrderSessionState.from_workflow(wf)

    messages = {
        OrderStep.LISTING: f"你之前查询了 {len(state.orders_snapshot)} 个订单，需要继续查看吗？",
        OrderStep.SELECTED: "你之前选择了一个订单，需要继续操作吗？",
        OrderStep.CONFIRMING: "上次的确认操作被中断，请重新操作。",
        OrderStep.IDLE: None,
    }

    msg = messages.get(state.current_step)
    return {
        "recovered": True,
        "state": state,
        "message": msg or "继续之前的话题？",
        "current_step": state.current_step.value,
    }
