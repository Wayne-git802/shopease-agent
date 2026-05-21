"""AgentLogger — unified logging for all AI agents.

Writes structured log entries to the AgentLog Django model and to
Python's logging module for real-time monitoring.

Design:
    log_request()   → creates a pending entry with all request context
    log_response()  → completes the pending entry with response data
    log_error()     → completes the pending entry with error info
    flush_to_db()   → bulk-writes all completed entries to MySQL
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

    # ── request ─────────────────────────────────────────────────

    def log_request(self, *, agent_type: str, trace_id: str,
                    user_id: Optional[int], summary: str) -> None:
        """Record the start of an agent invocation."""
        logger.info("[%s] %s REQUEST user=%s: %s",
                    trace_id, agent_type, user_id, summary)
        self._pending.append({
            'agent_type': agent_type,
            'trace_id': trace_id,
            'user_id': user_id,
            'request_summary': summary,
            'response_summary': '',
            'tokens_used': 0,
            'prompt_version': '',
            'latency_ms': 0,
            'cache_hit': False,
            'status': 'pending',      # not yet resolved
            'error': None,
        })

    # ── response (success) ──────────────────────────────────────

    def log_response(self, *, trace_id: str, tokens_used: int = 0,
                     cache_hit: bool = False, status: str = "ok",
                     prompt_version: str = "", latency_ms: int = 0,
                     response_summary: str = "") -> None:
        """Complete a pending log entry with response data."""
        for entry in self._pending:
            if entry['trace_id'] == trace_id and entry['status'] == 'pending':
                entry.update({
                    'tokens_used': tokens_used,
                    'cache_hit': cache_hit,
                    'status': status,
                    'prompt_version': prompt_version,
                    'latency_ms': latency_ms,
                    'response_summary': response_summary,
                })
                break
        else:
            # Orphan response — create a minimal entry anyway
            self._pending.append({
                'agent_type': '',
                'trace_id': trace_id,
                'user_id': None,
                'request_summary': '',
                'response_summary': response_summary,
                'tokens_used': tokens_used,
                'prompt_version': prompt_version,
                'latency_ms': latency_ms,
                'cache_hit': cache_hit,
                'status': status,
                'error': None,
            })

        logger.info("[%s] RESPONSE tokens=%d cache=%s status=%s latency=%dms",
                    trace_id, tokens_used, cache_hit, status, latency_ms)

    # ── error ───────────────────────────────────────────────────

    def log_error(self, trace_id: str, error: str,
                  latency_ms: int = 0) -> None:
        """Complete a pending log entry with error info."""
        for entry in self._pending:
            if entry['trace_id'] == trace_id and entry['status'] == 'pending':
                entry.update({
                    'status': 'failed',
                    'error': error,
                    'latency_ms': latency_ms,
                })
                break
        else:
            # Orphan error — create a minimal entry
            self._pending.append({
                'agent_type': '',
                'trace_id': trace_id,
                'user_id': None,
                'request_summary': '',
                'response_summary': '',
                'tokens_used': 0,
                'prompt_version': '',
                'latency_ms': latency_ms,
                'cache_hit': False,
                'status': 'failed',
                'error': error,
            })

        logger.error("[%s] ERROR (%dms): %s", trace_id, latency_ms, error)

    # ── persistence ─────────────────────────────────────────────

    def flush_to_db(self) -> int:
        """Persist all completed/in-progress log entries to the AgentLog model.

        Returns the number of entries flushed.
        Safe to call multiple times — only drains the pending buffer.
        """
        if not self._pending:
            return 0

        try:
            from agents.models import AgentLog
            entries = []
            for p in self._pending:
                entries.append(AgentLog(
                    trace_id=p['trace_id'],
                    agent_type=p['agent_type'],
                    user_id=p['user_id'],
                    request_summary=p['request_summary'],
                    response_summary=p['response_summary'],
                    tokens_used=p['tokens_used'],
                    prompt_version=p['prompt_version'],
                    latency_ms=p['latency_ms'],
                    cache_hit=p['cache_hit'],
                    status=p['status'],
                    error=p['error'],
                ))
            if entries:
                AgentLog.objects.bulk_create(entries)
                flushed = len(entries)
                logger.info("Flushed %d AgentLog entries to DB", flushed)
            else:
                flushed = 0
        except Exception as exc:
            logger.warning("Failed to flush AgentLog to DB: %s", exc)
            flushed = 0
        finally:
            self._pending.clear()

        return flushed
