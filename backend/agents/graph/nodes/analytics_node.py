"""
Analytics Node — wraps the legacy MetaAnalyzer.generate_report().

I/O Contract:
  Input:  state.parallel_results["analytics_days"]  (int, default 7)
  Output: state.tool_results["analytics"] = stats dict
          state.final_response = markdown report string
  side_effect: calls MetaAnalyzer.generate_report()
"""
import time

from ..state import AgentState, NodeTrace
from agents.meta.analyzer import MetaAnalyzer


def analytics_node(state: AgentState) -> AgentState:
    """Generate analytics report via legacy MetaAnalyzer."""
    start = time.time()

    days = state.parallel_results.get("analytics_days", 7)

    try:
        analyzer = MetaAnalyzer()
        result = analyzer.generate_report(days=days)
        state.tool_results["analytics"] = result["stats"]
        state.final_response = result["markdown"]
        state.error = None
    except Exception as e:
        state.tool_results["analytics"] = {}
        state.final_response = ""
        state.error = f"MetaAnalyzer.generate_report failed: {e}"

    state.current_node = "analytics"
    state.ui_message = "正在生成运营报告…"
    state.steps_done.append("analytics")

    state.trace.append(NodeTrace(
        node_name="analytics",
        model_name="",
        latency_ms=int((time.time() - start) * 1000),
    ))

    return state
