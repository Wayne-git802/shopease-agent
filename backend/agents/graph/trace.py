"""
Observability — persist NodeTrace to AgentLog DB and RuntimeTrace for UI.

Per-node trace records: tokens, latency, model, cache hits.
RuntimeTrace: user-facing phase timeline (product cognition, not engineering).
"""
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .state import NodeTrace

# ── Node → user-visible phase mapping ────────────────────────────
# Engineering node names map to product-cognition phases.

NODE_TO_PHASE = {
    "entry_router":   "understanding",
    "search_node":    "retrieving",
    "recommend_node": "matching",
    "merge_node":     "ranking",
    "response_node":  "explaining",
    "analytics_node": "analyzing",
    "order_node":     "processing",
    "ops_node":       "checking",
    "chat_node":      "responding",
    "fallback_node":  "responding",
}

PHASE_LABELS = {
    "understanding": "理解你的需求",
    "retrieving":    "检索相关商品",
    "matching":      "匹配你的偏好",
    "ranking":       "筛选最优选择",
    "explaining":    "生成推荐理由",
    "analyzing":     "分析数据",
    "processing":    "处理订单",
    "checking":      "检查系统",
    "responding":    "生成回复",
}


@dataclass
class PhaseRecord:
    """One phase in the user-visible timeline."""
    phase: str                     # "matching"
    label: str                     # "匹配你的偏好"
    status: str = "ok"             # "ok" | "skip" | "fallback"
    ms: int = 0
    detail: str = ""               # optional detail e.g. "FAISS 命中 324"


@dataclass
class RuntimeTrace:
    """Lightweight trace accumulator for the UI timeline."""
    phases: List[PhaseRecord] = field(default_factory=list)
    total_ms: int = 0
    _t0: float = 0.0
    _last: float = 0.0

    def start(self) -> "RuntimeTrace":
        self._t0 = self._last = time.time()
        self.phases = []
        return self

    def record(self, node_name: str, status: str = "ok",
               detail: str = "") -> "RuntimeTrace":
        phase = NODE_TO_PHASE.get(node_name, "responding")
        label = PHASE_LABELS.get(phase, phase)
        now = time.time()
        ms = int((now - self._last) * 1000)
        self._last = now
        self.phases.append(PhaseRecord(
            phase=phase, label=label, status=status, ms=ms, detail=detail,
        ))
        return self

    def finish(self) -> "RuntimeTrace":
        self.total_ms = int((time.time() - self._t0) * 1000)
        return self

    def to_dict(self) -> dict:
        return {
            "phases": [
                {"phase": p.phase, "label": p.label,
                 "status": p.status, "ms": p.ms, "detail": p.detail}
                for p in self.phases
            ],
            "total_ms": self.total_ms,
        }


# ── persist_trace (unchanged) ────────────────────────────────────

def persist_trace(traces: list[NodeTrace]) -> None:
    """Write all NodeTrace entries to AgentLog table."""
    if not traces:
        return

    import django; django.setup()
    from agents.models import AgentLog
    import uuid

    logs = []
    for t in traces:
        logs.append(AgentLog(
            trace_id=uuid.uuid4().hex[:16],
            agent_type=f"graph:{t.node_name}",
            tokens_used=t.prompt_tokens + t.completion_tokens,
            latency_ms=t.latency_ms,
            cache_hit=t.cache_hit,
            status="ok",
        ))

    AgentLog.objects.bulk_create(logs, batch_size=100)
