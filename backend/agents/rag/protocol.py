"""
Knowledge RAG Protocol — abstract interface for document retrieval.

All knowledge RAG implementations MUST implement this protocol.
Consumers (chat_node, etc.) depend on the protocol, not on ChromaDB.
"""

from abc import ABC, abstractmethod


class KnowledgeRetrieverProtocol(ABC):
    """Abstract document retrieval interface.

    Contract:
      - search(): given a query, return top-k document chunks with metadata.
      - index_documents(): (re)build the document index from a directory.
      - chunk_count: total number of indexed chunks (property).
    """

    @abstractmethod
    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Return [{"content": ..., "metadata": {...}, "score": ...}, ...].
        Score is cosine similarity (0–1, higher = more relevant).
        """

    @abstractmethod
    def index_documents(self, docs_dir: str) -> int:
        """Index all .md files from docs_dir. Returns total chunk count."""

    @property
    @abstractmethod
    def chunk_count(self) -> int:
        """Total indexed chunks."""
