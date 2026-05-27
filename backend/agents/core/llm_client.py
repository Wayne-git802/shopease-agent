"""LLM Client abstraction with Mock + DeepSeek implementations.

Usage:
    from agents.core.llm_client import get_llm_client
    llm = get_llm_client()  # reads LLM_MODE from Django settings
    response = llm.chat("Hello", tools=[...])
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import requests
from django.conf import settings

from .exceptions import LLMError, LLMTimeoutError, LLMRateLimitError


@dataclass
class LLMResponse:
    """Standard response from any LLM client."""
    text: str
    tokens_used: int = 0
    finish_reason: str = "stop"
    tool_calls: list = field(default_factory=list)


class LLMClient(ABC):
    """All agents depend on this interface — never on a concrete implementation."""

    @abstractmethod
    def chat(self, prompt: str, tools: Optional[list] = None,
             max_tokens: int = 2000) -> LLMResponse:
        """Send a prompt and return a structured response."""
        pass


# ---------------------------------------------------------------------------
# Mock — for development & testing (free, instant)
# ---------------------------------------------------------------------------

class MockLLMClient(LLMClient):
    """Returns canned responses. Zero cost, zero latency."""

    def __init__(self):
        self._call_count = 0

    def chat(self, prompt: str, tools: Optional[list] = None,
             max_tokens: int = 2000) -> LLMResponse:
        self._call_count += 1
        return LLMResponse(
            text=f"[Mock response #{self._call_count}] This is a simulated reply. "
                 f"In production this would be a real LLM response.",
            tokens_used=0,
        )


# ---------------------------------------------------------------------------
# DeepSeek — production client
# ---------------------------------------------------------------------------

class DeepSeekClient(LLMClient):
    """Calls DeepSeek API. Requires DEEPSEEK_API_KEY in settings."""

    def __init__(self):
        self.api_key = getattr(settings, 'DEEPSEEK_API_KEY', None) \
            or settings.DEEPSEEK_API_KEY
        self.base_url = getattr(settings, 'DEEPSEEK_BASE_URL',
                                'https://api.deepseek.com/v1')
        self.model = getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-chat')
        self.timeout = getattr(settings, 'LLM_TIMEOUT_SECONDS', 30)
        self.max_retries = getattr(settings, 'LLM_MAX_RETRIES', 2)

    def chat(self, prompt: str, tools: Optional[list] = None,
             max_tokens: int = 2000) -> LLMResponse:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        payload = {
            'model': self.model,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': max_tokens,
        }
        if tools:
            payload['tools'] = tools

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    f'{self.base_url}/chat/completions',
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                    proxies={'http': None, 'https': None},
                )
                if resp.status_code == 429:
                    raise LLMRateLimitError("DeepSeek rate limit exceeded")
                if resp.status_code != 200:
                    raise LLMError(
                        f"DeepSeek returned {resp.status_code}: {resp.text[:200]}")

                data = resp.json()
                choice = data['choices'][0]
                message = choice['message']
                return LLMResponse(
                    text=message.get('content', ''),
                    tokens_used=data.get('usage', {}).get('total_tokens', 0),
                    finish_reason=choice.get('finish_reason', 'stop'),
                    tool_calls=message.get('tool_calls', []),
                )
            except requests.Timeout:
                last_error = LLMTimeoutError("DeepSeek API timed out")
            except (LLMRateLimitError, LLMError):
                raise
            except Exception as e:
                last_error = LLMError(f"DeepSeek API error: {e}")

            if attempt < self.max_retries:
                import time
                time.sleep(2 ** attempt)

        raise last_error or LLMError("DeepSeek API failed after retries")


# ---------------------------------------------------------------------------
# Factory — the ONLY place that decides Mock vs Real
# ---------------------------------------------------------------------------

_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return the configured LLM client (singleton)."""
    global _client
    if _client is None:
        mode = getattr(settings, 'LLM_MODE', 'mock')
        if mode == 'production':
            _client = DeepSeekClient()
        else:
            _client = MockLLMClient()
    return _client


def reset_llm_client() -> None:
    """Reset the singleton (useful for tests)."""
    global _client
    _client = None
