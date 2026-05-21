"""AgentLogger — unified logging for all AI agents.

Writes structured log entries to the AgentLog Django model and optionally
to Python's logging module for real-time monitoring.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class AgentLogger:
    """Non-blocking logger that persists to DB and emits Python log records."""

    def __init__(self):
        self._pending: list[dict] = []

    def log_request(self, *, agent_type: str, trace_id: str,
                    user_id: Optional[int], summary: str) -> None:
        logger.info("[%s] %s REQUEST user=%s: %s",
                    trace_id, agent_type, user_id, summary)

    def log_response(self, *, trace_id: str, tokens_used: int = 0,
                     cache_hit: bool = False, status: str = "ok",
                     prompt_version: str = "") -> None:
        self._pending.append({
            'trace_id': trace_id,
            'tokens_used': tokens_used,
            'cache_hit': cache_hit,
            'status': status,
            'prompt_version': prompt_version,
        })
        logger.info("[%s] RESPONSE tokens=%d cache=%s status=%s",
                    trace_id, tokens_used, cache_hit, status)

    def log_error(self, trace_id: str, error: str) -> None:
        logger.error("[%s] ERROR: %s", trace_id, error)

    def flush_to_db(self) -> None:
        """Persist pending log records to the AgentLog Django model.

        Called at the end of a request cycle or periodically.
        Safe to call multiple times — only drains the pending buffer.
        """
        if not self._pending:
            return

        try:
            from agents.models import AgentLog
            entries = []
            for p in self._pending:
                entries.append(AgentLog(
                    trace_id=p['trace_id'],
                    tokens_used=p['tokens_used'],
                    cache_hit=p['cache_hit'],
                    status=p['status'],
                    prompt_version=p.get('prompt_version', ''),
                ))
            if entries:
                AgentLog.objects.bulk_create(entries)
        except Exception as exc:
            logger.warning("Failed to flush AgentLog to DB: %s", exc)
        finally:
            self._pending.clear()
