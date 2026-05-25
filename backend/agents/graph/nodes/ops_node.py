"""
Ops Node — wraps legacy monitors.py for system health monitoring (no LLM).

I/O Contract:
  Input:  OpsNodeInput  (check_type via parallel_results)
  Output: OpsNodeOutput (health, alerts)
  side_effect: DB reads only (deterministic, delegated to monitors.py)
"""
import time
import logging

from ..state import AgentState, NodeTrace

logger = logging.getLogger(__name__)


def ops_node(state: AgentState) -> AgentState:
    """System health check — delegates to agents.ops.monitors."""
    start = time.time()
    check_type = state.parallel_results.get("ops_check_type", "health")

    try:
        from agents.ops.monitors import get_health_summary, run_all_checks

        if check_type == "health":
            result = get_health_summary()
            state.tool_results["health"] = result
            state.final_response = f"System status: {result['status']}"
        elif check_type == "alerts":
            findings = run_all_checks()
            state.tool_results["findings"] = findings
        # else: unknown check_type — no-op, nothing written

    except Exception as e:
        logger.exception("ops_node failed via monitors")
        state.error = f"ops check failed: {e}"
        state.tool_results["ops"] = {"health": {}, "alerts": []}

    state.current_node = "ops"
    state.ui_message = "正在检查系统状态…"
    state.steps_done.append("ops")

    state.trace.append(NodeTrace(
        node_name="ops",
        model_name="",
        latency_ms=int((time.time() - start) * 1000),
    ))

    return state
