"""Memory Bridge — long-term cross-project user memory via Hermes state.db.

Architecture:
    Short-term  → AgentConversation (MySQL)
    Medium-term → UserPreference (MySQL)
    Long-term   → Hermes Memory (SQLite via this bridge)

This module reads/writes to Hermes's state.db (SQLite), providing
cross-project persistent memory that survives project changes.

The bridge creates its own table inside state.db:
    agent_memory(key TEXT PK, value TEXT, source_agent TEXT,
                 confidence REAL, created_at TEXT, updated_at TEXT)

Usage:
    bridge = MemoryBridge()
    bridge.set('user:1:preferred_color', '红色', source_agent='customer_service')
    color = bridge.get('user:1:preferred_color')

Graceful degradation:
    If state.db is unavailable → in-memory fallback (session-only)
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────

# Path to Hermes state.db
# On Windows: ~/AppData/Local/hermes/state.db
# On Linux/macOS: ~/.hermes/state.db
_HERMES_HOME = os.environ.get(
    'HERMES_HOME',
    str(Path.home() / 'AppData' / 'Local' / 'hermes')
)
DEFAULT_DB_PATH = os.path.join(_HERMES_HOME, 'state.db')

# Table name inside state.db
TABLE_NAME = 'agent_memory'

# DDL
_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    source_agent TEXT DEFAULT '',
    confidence   REAL DEFAULT 1.0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
)
"""


class MemoryBridge:
    """Bridge to Hermes long-term memory (SQLite).

    Thread-safe.  Falls back to in-memory dict if DB is unavailable.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self._fallback: dict[str, str] = {}  # in-memory fallback
        self._available: Optional[bool] = None
        self._ensure_table()

    # ── public API ──────────────────────────────────────────────

    def get(self, key: str) -> Optional[str]:
        """Retrieve a value by key. Returns None if not found."""
        with self._lock:
            if not self._ensure_available():
                return self._fallback.get(key)

            try:
                conn = sqlite3.connect(self._db_path)
                cur = conn.cursor()
                cur.execute(
                    f'SELECT value FROM {TABLE_NAME} WHERE key = ?', (key,))
                row = cur.fetchone()
                conn.close()
                return row[0] if row else None
            except Exception as exc:
                logger.warning("MemoryBridge.get(%s) failed: %s", key, exc)
                self._available = False
                return self._fallback.get(key)

    def get_json(self, key: str) -> Optional[dict]:
        """Retrieve a JSON value. Returns None if not found or invalid."""
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("MemoryBridge.get_json(%s): invalid JSON", key)
            return None

    def set(self, key: str, value: str, *,
            source_agent: str = '',
            confidence: float = 1.0) -> bool:
        """Store a value. Returns True on success."""
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            if not self._ensure_available():
                self._fallback[key] = value
                return True  # in-memory fallback counts as success

            try:
                conn = sqlite3.connect(self._db_path)
                cur = conn.cursor()
                cur.execute(
                    f'''INSERT INTO {TABLE_NAME}
                        (key, value, source_agent, confidence, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        source_agent=excluded.source_agent,
                        confidence=excluded.confidence,
                        updated_at=excluded.updated_at''',
                    (key, value, source_agent, confidence, now, now))
                conn.commit()
                conn.close()
                return True
            except Exception as exc:
                logger.warning("MemoryBridge.set(%s) failed: %s", key, exc)
                self._available = False
                self._fallback[key] = value
                return True  # fallback

    def set_json(self, key: str, data: dict, *,
                 source_agent: str = '',
                 confidence: float = 1.0) -> bool:
        """Store a JSON-serializable dict."""
        return self.set(key, json.dumps(data, ensure_ascii=False),
                        source_agent=source_agent, confidence=confidence)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True on success (or if key didn't exist)."""
        with self._lock:
            if not self._ensure_available():
                self._fallback.pop(key, None)
                return True

            try:
                conn = sqlite3.connect(self._db_path)
                cur = conn.cursor()
                cur.execute(f'DELETE FROM {TABLE_NAME} WHERE key = ?', (key,))
                conn.commit()
                conn.close()
                return True
            except Exception as exc:
                logger.warning("MemoryBridge.delete(%s) failed: %s", key, exc)
                self._available = False
                self._fallback.pop(key, None)
                return True

    def list_keys(self, prefix: str = '') -> list[str]:
        """List all keys, optionally filtered by prefix."""
        with self._lock:
            if not self._ensure_available():
                return [k for k in self._fallback if k.startswith(prefix)]

            try:
                conn = sqlite3.connect(self._db_path)
                cur = conn.cursor()
                if prefix:
                    cur.execute(
                        f'SELECT key FROM {TABLE_NAME} WHERE key LIKE ?',
                        (f'{prefix}%',))
                else:
                    cur.execute(f'SELECT key FROM {TABLE_NAME}')
                keys = [row[0] for row in cur.fetchall()]
                conn.close()
                return keys
            except Exception as exc:
                logger.warning("MemoryBridge.list_keys failed: %s", exc)
                self._available = False
                return [k for k in self._fallback if k.startswith(prefix)]

    def get_user_preferences(self, user_id: int) -> dict[str, str]:
        """Get all long-term preferences for a user.

        Returns a dict like {'preferred_color': '红色', 'budget': '200'}.
        """
        prefix = f'user:{user_id}:'
        prefs = {}
        for key in self.list_keys(prefix):
            short_key = key[len(prefix):]
            value = self.get(key)
            if value is not None:
                prefs[short_key] = value
        return prefs

    def set_user_preference(self, user_id: int, key: str, value: str,
                            source_agent: str = '',
                            confidence: float = 1.0) -> bool:
        """Store a user preference with namespaced key."""
        full_key = f'user:{user_id}:{key}'
        return self.set(full_key, value, source_agent=source_agent,
                        confidence=confidence)

    @property
    def available(self) -> bool:
        """Check if the bridge is using the real DB (vs fallback)."""
        self._ensure_available()
        return self._available is True

    # ── internal ────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        """Create the agent_memory table if it doesn't exist."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(_CREATE_TABLE)
            conn.commit()
            conn.close()
            self._available = True
            logger.debug("MemoryBridge table ready at %s", self._db_path)
        except Exception as exc:
            logger.warning("MemoryBridge init failed: %s. Using fallback.", exc)
            self._available = False

    def _ensure_available(self) -> bool:
        """Re-check availability if unknown."""
        if self._available is None:
            self._ensure_table()
        return self._available is True


# ── Singleton ───────────────────────────────────────────────────

_bridge: Optional[MemoryBridge] = None


def get_memory_bridge(db_path: Optional[str] = None) -> MemoryBridge:
    """Return the global MemoryBridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = MemoryBridge(db_path)
    return _bridge


def reset_memory_bridge() -> None:
    """Reset the singleton (useful for tests)."""
    global _bridge
    _bridge = None
