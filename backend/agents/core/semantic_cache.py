"""Semantic cache — first tier of the 3-tier token-saving strategy.

Workflow:
  1. User asks a question
  2. Embed the question with sentence-transformers (local, zero API cost)
  3. Search the SemanticCache MySQL table for similar questions
  4. If cosine similarity > THRESHOLD → return cached answer (0 token cost)
  5. If no match → return None → caller calls LLM → caches result

Architecture target: 30-40% cache hit rate for high-frequency questions.

Dependencies:
  - sentence-transformers (pip install sentence-transformers)
  - numpy (for cosine similarity)
  - agents.models.SemanticCache (MySQL)

Graceful degradation:
  - If sentence-transformers is not installed → cache disabled (always miss)
  - If MySQL is unavailable → cache disabled (always miss)
"""

import logging
import struct
from typing import Optional

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────────

# Cosine similarity threshold for cache hit (0.0 – 1.0)
SIMILARITY_THRESHOLD = getattr(settings, 'SEMANTIC_CACHE_THRESHOLD', 0.95)

# Model name for sentence-transformers (runs locally, no API key needed)
EMBEDDING_MODEL_NAME = getattr(
    settings, 'SEMANTIC_CACHE_MODEL',
    'paraphrase-multilingual-MiniLM-L12-v2'
)


class SemanticCache:
    """Semantic question → answer cache using local sentence-transformers.

    Usage:
        cache = SemanticCache()
        cached = cache.lookup('怎么退货？', agent_type='customer_service')
        if cached:
            return cached  # 0 tokens
        # ... call LLM ...
        cache.store('怎么退货？', llm_response, agent_type='customer_service')
    """

    def __init__(self):
        self._model = None
        self._model_error: Optional[str] = None

    # ── public API ──────────────────────────────────────────────

    def lookup(self, query: str, agent_type: str) -> Optional[str]:
        """Search the cache for a semantically similar question.

        Returns the cached response text, or None on cache miss.
        """
        embedding = self._embed(query)
        if embedding is None:
            return None

        try:
            from agents.models import SemanticCache as CacheModel

            # Fetch all cache entries for this agent type
            candidates = CacheModel.objects.filter(agent_type=agent_type)
            if not candidates.exists():
                return None

            best_score = 0.0
            best_response = None

            for entry in candidates.iterator():
                cached_emb = self._bytes_to_array(entry.query_embedding)
                if cached_emb is None:
                    continue
                score = self._cosine_similarity(embedding, cached_emb)
                if score > best_score and score >= SIMILARITY_THRESHOLD:
                    best_score = score
                    best_response = entry.response_text

            if best_response:
                logger.info("Cache HIT (sim=%.4f): %s → %s",
                            best_score, query[:60], best_response[:60])
            else:
                logger.debug("Cache MISS: %s", query[:60])

            return best_response

        except Exception as exc:
            logger.warning("Semantic cache lookup failed: %s", exc)
            return None

    def store(self, query: str, response: str, agent_type: str) -> bool:
        """Store a question-response pair in the semantic cache.

        Returns True on success, False on failure.
        """
        embedding = self._embed(query)
        if embedding is None:
            return False

        try:
            from agents.models import SemanticCache as CacheModel

            CacheModel.objects.create(
                query_embedding=self._array_to_bytes(embedding),
                query_text=query,
                response_text=response,
                agent_type=agent_type,
            )
            logger.debug("Cached: %s (agent=%s)", query[:60], agent_type)
            return True
        except Exception as exc:
            logger.warning("Failed to store in semantic cache: %s", exc)
            return False

    def clear(self, agent_type: Optional[str] = None) -> int:
        """Clear cache entries.  If agent_type is None, clear all.

        Returns the number of deleted entries.
        """
        try:
            from agents.models import SemanticCache as CacheModel
            qs = CacheModel.objects.all()
            if agent_type:
                qs = qs.filter(agent_type=agent_type)
            count, _ = qs.delete()
            logger.info("Cleared %d cache entries (agent=%s)", count, agent_type or 'all')
            return count
        except Exception as exc:
            logger.warning("Failed to clear cache: %s", exc)
            return 0

    @property
    def enabled(self) -> bool:
        """Check if the cache is operational."""
        return self._model_error is None and self._load_model() is not None

    # ── embedding ───────────────────────────────────────────────

    def _embed(self, text: str) -> Optional[np.ndarray]:
        """Convert text to a normalized embedding vector. Returns None on failure."""
        model = self._load_model()
        if model is None:
            return None
        try:
            emb = model.encode(text, normalize_embeddings=True)
            return np.asarray(emb, dtype=np.float32)
        except Exception as exc:
            logger.warning("Embedding failed: %s", exc)
            self._model_error = str(exc)
            return None

    def _load_model(self):
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return self._model
        if self._model_error is not None:
            return None

        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s ...", EMBEDDING_MODEL_NAME)
            self._model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded.")
            return self._model
        except ImportError:
            msg = "sentence-transformers not installed. Semantic cache disabled."
            self._model_error = msg
            logger.warning(msg)
            return None
        except Exception as exc:
            self._model_error = str(exc)
            logger.warning("Failed to load embedding model: %s", exc)
            return None

    # ── serialization ───────────────────────────────────────────

    @staticmethod
    def _array_to_bytes(arr: np.ndarray) -> bytes:
        """Convert numpy array to bytes for MySQL BinaryField."""
        # Format: [n_dims: uint32][float32 × n_dims]
        return struct.pack(f'I{len(arr)}f', len(arr), *arr)

    @staticmethod
    def _bytes_to_array(data: bytes) -> Optional[np.ndarray]:
        """Convert bytes from MySQL BinaryField back to numpy array."""
        try:
            n_dims = struct.unpack('I', data[:4])[0]
            floats = struct.unpack(f'{n_dims}f', data[4:])
            return np.array(floats, dtype=np.float32)
        except Exception as exc:
            logger.warning("Failed to deserialize embedding: %s", exc)
            return None

    # ── math ────────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors. Assumes both are normalized."""
        return float(np.dot(a, b))


# ── Singleton ───────────────────────────────────────────────────

_cache: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    """Return the global SemanticCache singleton."""
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


def reset_semantic_cache() -> None:
    """Reset the singleton (useful for tests)."""
    global _cache
    _cache = None
