"""
FAISS Vector Store — IndexFlatL2 wrapper with save/load.

Index maps product_id → vector (384-dim). Query returns top-k nearest.
Persists index to data/faiss_index.bin and id_map to data/faiss_id_map.json.
"""
import json
import os
from pathlib import Path

import faiss
import numpy as np

from .embedder import embed_dim

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_INDEX_PATH = _DATA_DIR / "faiss_index.bin"
_ID_MAP_PATH = _DATA_DIR / "faiss_id_map.json"


class VectorStore:
    """FAISS L2 index for product embeddings."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.index: faiss.IndexFlatL2 | None = None
        self.id_map: list[int] = []        # position → product_id

    @property
    def size(self) -> int:
        return self.index.ntotal if self.index else 0

    # ── Build ──────────────────────────────────────────────────

    def build(self, ids: list[int], vectors: np.ndarray) -> None:
        """Build index from scratch. vectors shape = (N, 384)."""
        vectors = vectors.astype(np.float32)
        self.index = faiss.IndexFlatL2(embed_dim())
        self.index.add(vectors)
        self.id_map = list(ids)
        self._save()  # Auto-save after build

    # ── Search ─────────────────────────────────────────────────

    def search(self, query_vec: np.ndarray, k: int = 10) -> list[tuple[int, float]]:
        """Return [(product_id, L2_distance), ...] sorted nearest-first."""
        if self.index is None or self.index.ntotal == 0:
            return []
        query_vec = query_vec.astype(np.float32).reshape(1, -1)
        distances, indices = self.index.search(query_vec, min(k, self.index.ntotal))
        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx < 0 or idx >= len(self.id_map):
                continue
            results.append((self.id_map[idx], float(distances[0][i])))
        return results

    # ── Persist ────────────────────────────────────────────────

    def _save(self) -> None:
        """Persist index and id_map to disk."""
        if self.index is None:
            return
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(_INDEX_PATH))
        with open(_ID_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(self.id_map, f)

    def _load(self) -> bool:
        """Load index and id_map from disk. Returns True if loaded."""
        if _INDEX_PATH.exists() and _ID_MAP_PATH.exists():
            self.index = faiss.read_index(str(_INDEX_PATH))
            with open(_ID_MAP_PATH, "r", encoding="utf-8") as f:
                self.id_map = json.load(f)
            return True
        return False

    def save(self, path: str | None = None) -> None:
        """Public save. Uses default data/ path if none given."""
        if path is not None:
            # Custom path — write index only (backward compat)
            if self.index is not None:
                faiss.write_index(self.index, path)
        else:
            self._save()

    def load(self, path: str | None = None) -> bool:
        """Public load. Uses default data/ path if none given."""
        if path is not None:
            if not os.path.exists(path):
                return False
            self.index = faiss.read_index(path)
            return True
        return self._load()

    def load_or_build(self, ids: list[int], vectors: np.ndarray) -> None:
        """Try loading from disk, fall back to building from scratch."""
        if not self._load():
            self.build(ids, vectors)


# ── Singleton ────────────────────────────────────────────────────

_store: VectorStore | None = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
        if not _store._load():
            # No persisted index — caller must build()
            pass
    return _store
