"""
RAG Protocol — abstract interface for retrieval.

All RAG implementations MUST implement this protocol.
Nodes depend on the protocol, not on a specific retriever.
"""
from abc import ABC, abstractmethod

import numpy as np

from ..state import ProductRef, DocRef


class RetrieverProtocol(ABC):
    """Abstract retrieval interface.

    Contract:
      - search(): given a query string, return top‑k products and docs.
      - embed(): convert text to vector (for external use, e.g. caching).
      - index_products(): (re)build the product index from the DB.
    """

    @abstractmethod
    def search(self, query: str, top_k: int = 10,
               user_id: int | None = None) -> tuple[list[ProductRef], list[DocRef]]:
        """Return (products, docs) ranked by relevance."""

    @abstractmethod
    def embed(self, text: str) -> np.ndarray:
        """Single-text embedding → 384‑dim vector."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Batch embedding → (N, 384) array."""

    @abstractmethod
    def index_products(self, product_texts: list[tuple[int, str]]) -> None:
        """Rebuild FAISS index from [(product_id, text), ...]."""

    @abstractmethod
    def save_index(self, path: str) -> None:
        """Persist FAISS index to disk."""

    @abstractmethod
    def load_index(self, path: str) -> None:
        """Load FAISS index from disk."""
