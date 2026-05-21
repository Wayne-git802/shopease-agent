"""Unified exceptions for the AI Agent system."""


class AgentError(Exception):
    """Base exception for all agent-related errors."""
    pass


class LLMError(AgentError):
    """LLM API call failed."""
    pass


class LLMTimeoutError(LLMError):
    """LLM API call timed out."""
    pass


class LLMRateLimitError(LLMError):
    """LLM API rate limit exceeded."""
    pass


class AgentToolError(AgentError):
    """Agent tool execution failed."""
    pass


class AgentPermissionError(AgentError):
    """Agent attempted an unauthorized action."""
    pass


class AgentCircuitBreakerError(AgentError):
    """Circuit breaker is open — too many failures."""
    pass


class AgentMaxDepthError(AgentError):
    """Cross-agent call depth exceeded limit."""
    pass


class AgentBudgetExceededError(AgentError):
    """Token budget exceeded for this request."""
    pass
