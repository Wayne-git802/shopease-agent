"""BaseAgent — abstract base class for all agents.

Every agent in the system inherits from this class.  It provides:
  - LLM client injection (Mock or DeepSeek — agent doesn't care)
  - Agent logger integration
  - Common lifecycle hooks
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .llm_client import LLMClient, LLMResponse, get_llm_client
from .agent_logger import AgentLogger


@dataclass
class AgentContext:
    """Context passed into every agent.process() call."""
    user_id: Optional[int] = None
    session_id: str = ""
    trace_id: str = ""
    max_depth: int = 2
    caller_chain: list = field(default_factory=list)
    user_preferences: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    """Standard result from every agent."""
    status: str            # "ok" | "degraded" | "failed"
    data: dict = field(default_factory=dict)
    text: str = ""
    error: Optional[str] = None
    tokens_used: int = 0
    cache_hit: bool = False


class BaseAgent(ABC):
    """Abstract base for all agents.

    Subclasses implement `_process()` — never `process()` directly.
    `process()` is the public entry point that handles logging, error
    wrapping, and budget tracking.
    """

    agent_type: str = "base"   # override in subclass

    def __init__(self, llm_client: Optional[LLMClient] = None,
                 logger: Optional[AgentLogger] = None):
        self.llm = llm_client or get_llm_client()
        self.logger = logger or AgentLogger()

    # ── public API ──────────────────────────────────────────────

    def process(self, user_input: str, context: AgentContext) -> AgentResult:
        """Public entry point.  Handles logging + error wrapping."""
        self.logger.log_request(
            agent_type=self.agent_type,
            trace_id=context.trace_id,
            user_id=context.user_id,
            summary=user_input[:200],
        )
        try:
            result = self._process(user_input, context)
            self.logger.log_response(
                trace_id=context.trace_id,
                tokens_used=result.tokens_used,
                cache_hit=result.cache_hit,
                status=result.status,
            )
            return result
        except Exception as exc:
            self.logger.log_error(context.trace_id, str(exc))
            return AgentResult(
                status="failed",
                error=str(exc),
                tokens_used=0,
            )

    # ── subclass contract ───────────────────────────────────────

    @abstractmethod
    def _process(self, user_input: str, context: AgentContext) -> AgentResult:
        """Implement this in every agent subclass."""
        pass

    # ── helpers ─────────────────────────────────────────────────

    def _llm_chat(self, prompt: str, tools: Optional[list] = None,
                  max_tokens: int = 2000) -> LLMResponse:
        """Convenience wrapper around self.llm.chat()."""
        return self.llm.chat(prompt, tools=tools, max_tokens=max_tokens)
