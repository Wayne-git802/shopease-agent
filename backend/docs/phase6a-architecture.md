# Phase 6a 最终架构

## 设计决策

| 决策 | 结论 |
|------|------|
| save 责任 | Phase 6a 只做 read facade，Agent 内部写逻辑不动 |
| WorkflowState | lazy load，创建时不查 DB |
| SharedView | 请求级缓存，handoff loop 内不过 DB |
| AgentMemory | 非单例，每次请求 `AgentMemory()` |
| AgentContext | 非单例，`from_pipeline()` 工厂创建 |
| can_handle | 仍收 PipelineContext（需要 commerce_result） |
| execute | 收 AgentContext（只需要记忆+输入） |
| SessionState 写 | field-level merge（不覆盖整行） |

## 分层

```
Agent (OrderAgent, CartAgent, PurchaseAgent)
    │  ctx.memory.recall_workflow(session_id)
    ▼
AgentMemory (facade，请求级实例，持有请求级缓存)
    │
    ▼
MemoryService (薄中间层，Phase 6 直通 backend)
    │
    ▼
MemoryBackend (纯存储，无状态，公开 API)
    │
    ▼
现有模块 (workflow_store, session_memory, memory.py)
```

## 文件结构

```
agents/graph/memory/
├── __init__.py           AgentMemory + MemoryService (~100行)
├── backend.py            MemoryBackend + DefaultMemoryBackend (~100行)
└── types.py              WorkflowState(lazy) + SharedView + MemoryEvent (~55行)
```

## types.py

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from agents.order.workflow_store import OrderWorkflow
    from agents.cart.agent import CartSessionState
    from agents.purchase.workflow_store import PurchaseWorkflow as PurchaseWF

_MISSING = object()


@dataclass
class WorkflowState:
    """Lazy workflow states. One DB query per property, not per creation."""

    _session_id: str
    _backend: "MemoryBackend"

    _order: Any = _MISSING
    _cart: Any = _MISSING
    _purchase: Any = _MISSING

    @property
    def order(self) -> "OrderWorkflow | None":
        if self._order is _MISSING:
            self._order = self._backend.load_workflow_item(self._session_id, "order")
        return self._order

    @property
    def cart(self) -> "CartSessionState | None":
        if self._cart is _MISSING:
            self._cart = self._backend.load_workflow_item(self._session_id, "cart")
        return self._cart

    @property
    def purchase(self) -> "PurchaseWF | None":
        if self._purchase is _MISSING:
            self._purchase = self._backend.load_workflow_item(self._session_id, "purchase")
        return self._purchase


@dataclass
class SharedView:
    """Cross-agent shared context. System-owned, not agent-owned.

    WorkflowState = what one agent is doing.
    SharedView   = what other agents need to see.
    """

    current_product: dict | None = None
    cart_snapshot: list[dict] = field(default_factory=list)


@dataclass
class MemoryEvent:
    """Audit/debug/replay. Phase 6: definition only, not wired."""
    type: str
    session_id: str
    user_id: int | None
    payload: dict
    timestamp: float
```

## backend.py

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class MemoryBackend(Protocol):
    """Pluggable memory backend. Public API — all methods usable by domain layer."""

    # Workflow per-agent items
    def load_workflow_item(self, session_id: str, agent_type: str) -> Any:
        ...

    # Session
    def recall_session(self, session_id: str) -> Any:
        ...

    def save_session(self, session_id: str, **kwargs) -> None:
        ...

    # User
    def recall_user(self, user_id: int) -> Any:
        ...

    # Shared View
    def recall_shared_view(self, session_id: str) -> "SharedView":
        ...

    def save_shared_view(self, session_id: str, view: "SharedView") -> None:
        ...


class DefaultMemoryBackend:
    """Production backend wrapping existing DB modules."""

    def load_workflow_item(self, session_id, agent_type):
        if agent_type == "order":
            from agents.order.workflow_store import load as load_owf
            return load_owf(session_id)
        elif agent_type == "cart":
            from agents.cart.agent import _load_state
            return _load_state(session_id)
        elif agent_type == "purchase":
            from agents.purchase.workflow_store import load as load_pwf
            return load_pwf(session_id)
        return None

    def recall_session(self, session_id):
        from agents.graph.session_memory import get as get_session
        return get_session(session_id)

    def save_session(self, session_id, **kwargs):
        # Field-level merge via update_or_create
        from agents.models import SessionState
        SessionState.objects.update_or_create(
            session_id=session_id,
            defaults={k: v for k, v in kwargs.items() if v is not None},
        )

    def recall_user(self, user_id):
        from agents.graph.memory import memory_manager
        return memory_manager.build(user_id)

    def recall_shared_view(self, session_id) -> "SharedView":
        from agents.models import SessionState
        row = SessionState.objects.filter(session_id=session_id).first()
        if row and row.shared_view:
            return SharedView(**row.shared_view)
        return SharedView()

    def save_shared_view(self, session_id, view: "SharedView"):
        from agents.models import SessionState
        # Field-level merge — only updates shared_view, leaves other fields
        SessionState.objects.update_or_create(
            session_id=session_id,
            defaults={"shared_view": {
                "current_product": view.current_product,
                "cart_snapshot": view.cart_snapshot,
            }},
        )
```

## __init__.py

```python
from dataclasses import dataclass, field
from .backend import MemoryBackend, DefaultMemoryBackend
from .types import WorkflowState, SharedView, _MISSING


class MemoryService:
    """Thin middle layer. Phase 6: pass-through. Phase 6b: cache/events."""

    def __init__(self, backend: MemoryBackend):
        self._b = backend

    def recall_workflow(self, session_id) -> WorkflowState:
        return WorkflowState(_session_id=session_id, _backend=self._b)

    def recall_session(self, session_id):
        return self._b.recall_session(session_id)

    def save_session(self, session_id, **kwargs):
        self._b.save_session(session_id, **kwargs)

    def recall_user(self, user_id):
        return self._b.recall_user(user_id)

    def recall_shared_view(self, session_id) -> SharedView:
        return self._b.recall_shared_view(session_id)

    def save_shared_view(self, session_id, view: SharedView):
        self._b.save_shared_view(session_id, view)


class AgentMemory:
    """Request-scoped memory facade. One instance per pipeline invocation.

    Holds request-level cache for Shared View — inside a handoff loop,
    set_shared_view writes cache first, DB as backup.
    """

    def __init__(self, backend: MemoryBackend | None = None):
        self._b = backend or DefaultMemoryBackend()
        self._service = MemoryService(self._b)
        self._shared_cache: dict[str, SharedView] = {}

    # Workflow
    def recall_workflow(self, session_id: str) -> WorkflowState:
        return self._service.recall_workflow(session_id)

    # Session
    def recall_session(self, session_id: str):
        return self._service.recall_session(session_id)

    def save_session(self, session_id: str, **kwargs) -> None:
        self._service.save_session(session_id, **kwargs)

    # User
    def recall_user(self, user_id: int):
        return self._service.recall_user(user_id)

    # Shared View (request-level cache)
    def get_shared_view(self, session_id: str) -> SharedView:
        if session_id in self._shared_cache:
            return self._shared_cache[session_id]
        view = self._service.recall_shared_view(session_id)
        self._shared_cache[session_id] = view
        return view

    def set_shared_view(self, session_id: str, **kwargs) -> None:
        if session_id not in self._shared_cache:
            self._shared_cache[session_id] = SharedView()
        for k, v in kwargs.items():
            setattr(self._shared_cache[session_id], k, v)
        self._service.save_shared_view(session_id, self._shared_cache[session_id])
```

## pipeline.py 改动

```python
@dataclass
class AgentContext:
    """Standard input passed to every agent during execute()."""

    query: str
    user_id: int | None
    session_id: str
    display_id: str = ""
    memory: AgentMemory = field(default_factory=AgentMemory)

    @classmethod
    def from_pipeline(cls, ctx: PipelineContext) -> "AgentContext":
        from agents.graph.memory import AgentMemory
        return cls(
            query=ctx.query,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            display_id=ctx.display_id,
            memory=AgentMemory(),
        )


class AgentExecutor(Protocol):
    capability: AgentCapability
    priority: int = 0

    def can_handle(self, ctx: PipelineContext) -> bool:   # 不变 — 需要 commerce_result
        ...

    def execute(self, ctx: AgentContext) -> AgentResult:   # PipelineContext → AgentContext
        ...
```

## execution/__init__.py 改动

```python
def run(ctx: PipelineContext) -> AgentResult:
    from ..pipeline import AgentContext

    agent_ctx = AgentContext.from_pipeline(ctx)   # 构建一次

    while True:
        if ctx.handoff:
            result = dispatch(ctx.handoff.target, agent_ctx)   # 传 AgentContext
            ctx.handoff = None
        else:
            executor = resolve(ctx)
            if executor is not None:
                result = executor.execute(agent_ctx)           # 传 AgentContext
            else:
                result = graph_execute(agent_ctx)              # 传 AgentContext
        ...
```

## Agent 改动（以 CartAgent 为例）

```python
class CartAgent:
    capability = AgentCapability.CART
    priority = 10

    def can_handle(self, ctx: PipelineContext) -> bool:        # 不变
        commerce = ctx.commerce_result
        return bool(commerce and commerce.intent == "cart" and commerce.confidence >= 0.3)

    def execute(self, ctx: AgentContext) -> AgentResult:       # PipelineContext → AgentContext
        wf = ctx.memory.recall_workflow(ctx.session_id)        # 通过 memory 读
        result = run(ctx.query, ctx.user_id, ctx.session_id, ctx.display_id)

        if result.get("_handoff") == "purchase":
            ctx.memory.set_shared_view(                        # 写 SharedView
                ctx.session_id,
                cart_snapshot=result.get("metadata", {}).get("cart_snapshot", []),
            )
            return AgentResult(
                status="handoff",
                handoff=Handoff(target=AgentCapability.PURCHASE, ...),
            )

        if result.get("_fallback"):
            return AgentResult(status="fallback")
        return AgentResult(status="success", response=result)
```

## graph_executor.py 改动

```python
def execute(ctx: AgentContext) -> AgentResult:         # PipelineContext → AgentContext
    ...

def _base_response(ctx: AgentContext, ...) -> dict:    # 同步改
    ...

def _execute_template(ctx: AgentContext) -> AgentResult:
    ...

def _execute_llm_direct(ctx: AgentContext) -> AgentResult:
    ...

def _execute_graph(ctx: AgentContext, plan) -> AgentResult:
    ...
```

## models.py 改动

```python
class SessionState(models.Model):
    session_id = models.CharField(max_length=128, primary_key=True)
    pending_intent = models.CharField(max_length=64, default="")
    collected_slots = models.JSONField(default=dict)
    missing_slots = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    # Phase 6a 新增
    current_product = models.JSONField(null=True, blank=True)
    cart_snapshot = models.JSONField(null=True, blank=True)
    shared_view = models.JSONField(default=dict)  # 备选：统一用 shared_view 包含上面两个
```

## 改动清单

| 文件 | 改动 | 行数 |
|------|------|------|
| `agents/graph/memory/types.py` | 新增 | ~55 |
| `agents/graph/memory/backend.py` | 新增 | ~100 |
| `agents/graph/memory/__init__.py` | 新增 | ~100 |
| `agents/models.py` | SessionState +2 JSONField | +5 |
| `agents/migrations/` | 自动生成 | auto |
| `agents/graph/pipeline.py` | AgentContext + AgentExecutor 协议改 | +30 |
| `agents/graph/execution/__init__.py` | run() 构建 AgentContext | +5 |
| `agents/graph/execution/graph_executor.py` | 全部签名 PipelineContext→AgentContext | ~15 |
| `agents/order/agent.py` | execute 签名 + ctx.memory | ~10 |
| `agents/cart/agent.py` | execute 签名 + ctx.memory + set_shared_view | ~15 |
| `agents/purchase/agent.py` | execute 签名 + ctx.memory | ~10 |

**合计: 3 新文件 + 1 migration + 8 改动文件 + ~345 行**

## 验收标准

- [ ] `can_handle` 仍收 PipelineContext
- [ ] `execute` 收 AgentContext
- [ ] Agent 通过 `ctx.memory.recall_workflow()` 读工作流
- [ ] WorkflowState 为 lazy load，创建时不查 DB
- [ ] SharedView 请求级缓存，handoff loop 内不过 DB
- [ ] `cart_snapshot` 在 handoff 时写入 SharedView
- [ ] PurchaseAgent 能读到 CartAgent 写的 `cart_snapshot`
- [ ] 69 existing tests 全绿
- [ ] `graph_executor.py` 内部函数签名同步更新
