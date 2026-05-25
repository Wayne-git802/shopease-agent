
# Phase A: AI Runtime 产品化 — 架构设计

## 概述

让 AI Runtime "可见"：用户看到认知过程，开发者看到运行指标。

**硬边界：** 不做 SSE streaming、不做 websocket、不做实时监控、不做复杂图表。

---

## 一、数据流

```
用户输入 "推荐耳机"
  │
  ▼
workspace.html → submitWorkspace()
  │
  ▼
POST /api/agents/ai/    (ai_entry view)
  │
  ▼
agents/graph/orchestrator.py :: run()
  │  ┌─ entry_router   ─→ 阶段1: 理解需求     [打 timestamp]
  │  ├─ search_node    ─→ 阶段2: 检索商品     [打 timestamp]
  │  ├─ recommend_node ─→ 阶段3: 匹配偏好     [打 timestamp]
  │  ├─ merge_node     ─→ 阶段4: 筛选最优     [打 timestamp]
  │  └─ response_node  ─→ 阶段5: 生成推荐理由 [打 timestamp]
  │
  ▼  返回 state + trace
  │
  ▼
views.py :: ai_entry 组装响应
  │  runtime.phases  ← trace.phases (映射 node→phase)
  │  explain.factors ← 从 recommend_node state 提取
  │  retrieval       ← 从 search_node state 提取
  │
  ▼  JSON response
  │
  ▼
workspace.html :: renderRuntimePanel()
  │  展示: 时间线 + 推荐理由 + 检索概要
  │
  ▼
用户看到 AI 如何思考
```

---

## 二、后端设计

### 2.1 RuntimeTrace（trace.py 新增）

```python
from dataclasses import dataclass, field
from typing import List
import time

# Node → 用户可见 phase 映射表
NODE_TO_PHASE = {
    "entry_router":   "understanding",
    "search_node":    "retrieving",
    "recommend_node": "matching",
    "merge_node":     "ranking",
    "response_node":  "explaining",
}

PHASE_LABELS = {
    "understanding": "理解你的需求",
    "retrieving":    "检索相关商品",
    "matching":      "匹配你的偏好",
    "ranking":       "筛选最优选择",
    "explaining":    "生成推荐理由",
}

@dataclass
class PhaseRecord:
    phase: str        # "matching"
    label: str        # "匹配你的偏好"
    status: str       # "ok" | "skip" | "fallback"
    ms: int           # 耗时毫秒
    detail: str = ""  # 可选细节（如 "FAISS 命中 324"）

@dataclass  
class RuntimeTrace:
    phases: List[PhaseRecord] = field(default_factory=list)
    total_ms: int = 0
    _start_ts: float = 0.0
    
    def start(self):
        self._start_ts = time.time()
        self.phases = []
    
    def record(self, node_name: str, status: str = "ok", detail: str = ""):
        phase = NODE_TO_PHASE.get(node_name, node_name)
        now = time.time()
        # ms since self._start_ts or since last record
        elapsed = int((now - self._start_ts) * 1000) if self.phases else 0
        prev_end = self._start_ts
        if self.phases:
            # 近似：用累计时间 - 前面各阶段累计
            pass
        self.phases.append(PhaseRecord(
            phase=phase,
            label=PHASE_LABELS.get(phase, phase),
            status=status,
            ms=elapsed,
            detail=detail
        ))
    
    def finish(self):
        self.total_ms = int((time.time() - self._start_ts) * 1000)
        return self
```

### 2.2 orchestrator.py 修改点

```python
def run(query, user_id, session_id, query_type, product_id):
    trace = RuntimeTrace()
    trace.start()
    
    # ... 现有逻辑不变 ...
    
    # Node 1
    trace.record("entry_router")
    route = entry_router(state)
    state = {**state, **route}
    
    # Node 2 (根据路由)
    node_name = f"{routed_intent}_node"
    trace.record(node_name, detail=...)
    
    # ...
    
    trace.finish()
    result['trace'] = trace  # 新增
    return result
```

### 2.3 views.py ai_entry 修改

在现有返回 dict 中追加 3 个字段：

```python
# 组装 runtime
trace_data = result.get('trace')
runtime = {
    "phases": [
        {"phase": p.phase, "label": p.label, "status": p.status, "ms": p.ms}
        for p in trace_data.phases
    ],
    "total_ms": trace_data.total_ms
} if trace_data else None

# 组装 explain
explain = {
    "title": "为什么推荐这些？",
    "factors": result.get('explain_factors', [])
} if result.get('explain_factors') else None

# 组装 retrieval
retrieval_info = result.get('retrieval_info')
retrieval = {
    "summary": "基于商品描述、评论和相似商品分析",
    "detail": retrieval_info or ""
} if retrieval_info else None

return Response({
    # ... 现有字段 ...
    "runtime": runtime,
    "explain": explain,
    "retrieval": retrieval,
})
```

### 2.4 EvaluationEvent 模型（agents/models.py 新增）

```python
class EvaluationEvent(models.Model):
    session_id   = models.CharField(max_length=64, db_index=True)
    query_type   = models.CharField(max_length=32)  # recommend/search/chat/clarify
    event_type   = models.CharField(max_length=32)  # impression/click/dismiss/skip/clarify
    product_id   = models.IntegerField(null=True, blank=True)
    duration_ms  = models.IntegerField(null=True, blank=True)
    outcome_type = models.CharField(max_length=32, default='')  # clicked/purchased/ignored/abandoned/refined_query/clarified
    success      = models.BooleanField(default=False)
    metadata     = models.JSONField(default=dict, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'ai_evaluation_events'
        indexes = [
            models.Index(fields=['query_type', 'created_at']),
            models.Index(fields=['event_type', 'success']),
            models.Index(fields=['outcome_type']),
        ]
```

### 2.5 埋点 API 端点

```
POST /api/agents/eval/track/
{
    "session_id": "abc123",
    "query_type": "recommend", 
    "event_type": "click",
    "product_id": 42,
    "outcome_type": "clicked",
    "duration_ms": 25000,
    "success": true
}
```

视图放在 `agents/customer_service/views.py`，简单 CRUD，不参与 graph 流程。

### 2.6 Admin Dashboard 视图

```
GET /ai/runtime/   →  templates/ai/runtime.html
```

上下文数据由 `templates/views.py::ai_runtime()` 提供：

```python
def ai_runtime(request):
    from agents.models import EvaluationEvent
    from django.db.models import Count, Avg, Q
    from django.db.models.functions import TruncHour
    
    # 最近 50 条请求
    recent = EvaluationEvent.objects.filter(
        event_type='impression'
    ).order_by('-created_at')[:50]
    
    # 基础指标
    total = EvaluationEvent.objects.filter(event_type='impression').count()
    fallback_count = EvaluationEvent.objects.filter(event_type='fallback').count()
    clarify_trigger = EvaluationEvent.objects.filter(event_type='clarify_ask').count()
    clarify_success = EvaluationEvent.objects.filter(event_type='clarify_answer').count()
    
    avg_duration = EvaluationEvent.objects.filter(
        event_type='impression'
    ).aggregate(avg=Avg('duration_ms'))['avg'] or 0
    
    # 按意图分布
    intents = EvaluationEvent.objects.filter(
        event_type='impression'
    ).values('query_type').annotate(count=Count('id')).order_by('-count')
    
    return render(request, 'ai/runtime.html', {
        'recent_events': recent,
        'total_requests': total,
        'fallback_rate': round(fallback_count / max(total, 1) * 100, 1),
        'clarify_trigger_rate': round(clarify_trigger / max(total, 1) * 100, 1),
        'clarify_success_rate': round(clarify_success / max(clarify_trigger, 1) * 100, 1),
        'avg_latency_ms': int(avg_duration),
        'intents': intents,
    })
```

---

## 三、前端设计

### 3.1 Workspace Runtime 面板

位置：`workspace.html` 结果区下方，`tracePanel` 上面。

DOM 结构：
```html
<div id="runtimePanel" class="runtime-panel hidden">
    <!-- 时间线 -->
    <div class="runtime-timeline" id="runtimeTimeline">
        <!-- JS 动态生成 -->
    </div>
    
    <!-- 解释 -->
    <div class="explain-section hidden" id="explainSection">
        <!-- JS 动态生成 -->
    </div>
    
    <!-- 检索概要 -->
    <div class="retrieval-summary hidden" id="retrievalSummary">
        <!-- JS 动态生成 -->
    </div>
</div>
```

每个 phase 渲染为一个行：
```
● 理解你的需求        ✓  12ms
● 检索相关商品        ✓  45ms
● 匹配你的偏好        ✓  31ms
● 筛选最优选择        ✓   5ms
● 生成推荐理由        ✓  18ms
─────────────────────────
          总计 111ms
```

### 3.2 Dashboard 页面

`templates/ai/runtime.html`，继承 `base.html`。

4 块内容：
1. 指标卡片行（3 个）：平均延迟 / 回退率 / 追问成功率
2. 最近请求列表（表格，每行：查询内容 | 意图 | 耗时 | 状态）
3. 意图分布柱状图（纯 CSS bar chart，不外引库）
4. 追问拆分明细（trigger_rate / success_rate）

不搞复杂：纯 HTML + inline CSS + 少量 JS 从 Django 模板变量渲染。

### 3.3 埋点 JS

在 `workspace.html` 的现有 JS 中追加：

```javascript
// 埋点：impression
function trackImpression(data) { ... POST /api/agents/eval/track/ }

// 埋点：click（卡片点击时）
function trackClick(productId) { ... }

// 埋点：dismiss
function trackDismiss() { ... }
```

---

## 四、改动文件确认

| # | 文件 | 类型 | 内容 |
|---|------|------|------|
| 1 | `agents/graph/trace.py` | 改 | 新增 RuntimeTrace + NODE_TO_PHASE 映射 |
| 2 | `agents/graph/orchestrator.py` | 改 | 打 timestamp，推入 trace |
| 3 | `agents/customer_service/views.py` | 改 | ai_entry 注入 runtime/explain/retrieval + eval_track 端点 |
| 4 | `agents/models.py` | 改 | EvaluationEvent 模型 |
| 5 | `agents/urls.py` | 改 | 新增 eval/track/ 路由 |
| 6 | `mysite/urls.py` | 改 | 新增 /ai/runtime/ 路由 |
| 7 | `templates/views.py` | 改 | ai_runtime 视图 |
| 8 | `templates/ai/workspace.html` | 改 | Runtime 面板 + 埋点 JS |
| 9 | `templates/ai/runtime.html` | **新** | Admin Dashboard |
| 10 | `templates/static/css/ai.css` | 改 | 面板/Dashboard/bar-chart 样式 |

---

## 五、自检

### 耦合
- trace.py ↔ orchestrator.py：单向依赖，trace 是纯数据类，orchestrator 只调 record()
- views.py ↔ trace：views 读 trace.phases 映射 → 不耦合到 node 实现
- 埋点系统：完全独立，不影响现有 graph 流程
- ✅ 低耦合

### 失败
- trace.record() 失败 → 不影响 graph 原有逻辑，静默跳过
- 埋点 POST 失败 → 前端 catch 不抛错
- AI runtime 响应缺少 runtime/explain/retrieval → 前端检测 null 不渲染面板
- ✅ 优雅降级

### 扩展
- 加新 node → 在 NODE_TO_PHASE 加一行映射即可
- 加新指标 → 在 ai_runtime 视图多查一个 query
- 加新埋点事件 → EvaluationEvent 的 event_type 是字符串，不须改模型
- ✅ 高扩展性

### 边界
- 不做 SSE/streaming
- 不做 websocket/实时
- Dashboard 不做复杂图表
- 10 个文件，1 个新文件
- ✅ 硬边界清晰

### 维护
- Django 模型，自动 migrate
- 前端纯 vanilla JS，零外库
- CSS 追加在 ai.css，不影响现有样式
- ✅ 低维护成本

---

自检结论：✅ 五维通过，可以开始实现。
