"""
Embedder — text → vector using all-MiniLM-L6-v2 (384 dims).

Lazy-loaded singleton — 80MB model, loaded once at first use.
"""
import numpy as np
from sentence_transformers import SentenceTransformer

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_embedder: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        import os
        # HF is blocked in China — force offline to avoid 10060 timeout
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        _embedder = SentenceTransformer(_MODEL_NAME, local_files_only=True)
    return _embedder


def embed(text: str) -> np.ndarray:
    """Single text → (384,) float32 vector."""
    return _get_model().encode(text, normalize_embeddings=True).astype(np.float32)


def embed_batch(texts: list[str]) -> np.ndarray:
    """Batch texts → (N, 384) float32 array."""
    return _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False).astype(np.float32)


def embed_dim() -> int:
    return 384
