"""
KnowledgeStore — document chunking, embedding, and retrieval via ChromaDB.

Usage:
    ks = get_knowledge_store()               # singleton (preferred)
    ks.index_documents("docs")               # one-time indexing
    docs = ks.search("怎么退货", top_k=3)     # retrieval

Uses the same SentenceTransformer model as agents.graph.rag.embedder
(paraphrase-multilingual-MiniLM-L12-v2, 384-dim, normalized).
"""
import os
import re
from pathlib import Path

import chromadb

from ..graph.rag.embedder import embed, embed_batch, embed_dim
from .protocol import KnowledgeRetrieverProtocol

# ── Persist directory (relative to project root) ───────────────────
_DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent.parent / "chroma_knowledge"


class KnowledgeStore(KnowledgeRetrieverProtocol):
    """Document knowledge base backed by ChromaDB with cosine-similarity search."""

    def __init__(self, persist_dir: str | None = None):
        _dir = persist_dir if persist_dir else str(_DEFAULT_PERSIST_DIR)
        self.client = chromadb.PersistentClient(path=_dir)
        self.collection = self.client.get_or_create_collection(
            "knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )

    # ── Indexing ───────────────────────────────────────────────────

    def index_documents(self, docs_dir: str = "docs") -> int:
        """遍历 docs/ 下所有 .md 文件，chunk、embed、存入 ChromaDB。

        Returns the total number of chunks indexed.
        """
        docs_path = Path(docs_dir)
        if not docs_path.exists():
            return 0

        total = 0
        for md_file in sorted(docs_path.glob("*.md")):
            total += self._index_file(md_file)
        return total

    def _index_file(self, file_path: Path) -> int:
        """Index a single markdown file. Returns chunk count."""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        source = file_path.name

        # Split into chunks with section metadata
        chunks = self._chunk_markdown(content, source)
        if not chunks:
            return 0

        # Remove old entries for this source (idempotent re-index)
        existing = self.collection.get(where={"source": source})
        if existing and existing.get("ids"):
            self.collection.delete(ids=existing["ids"])

        ids = []
        documents = []
        metadatas = []

        for i, (section, text) in enumerate(chunks):
            ids.append(f"{source}_{i}")
            documents.append(text)
            metadatas.append({"source": source, "section": section})

        # Embed and store
        vectors = embed_batch(documents)
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=vectors.tolist(),
        )

        return len(chunks)

    # ── Chunking ───────────────────────────────────────────────────

    def _chunk_markdown(self, content: str, source: str) -> list[tuple[str, str]]:
        """Split markdown into (section_name, chunk_text) pairs.

        Strategy:
        1. Split the document by ## sections to track which heading each
           paragraph belongs to.
        2. Within each section, split by double-newlines into paragraphs.
        3. Merge consecutive paragraphs into chunks of 300–500 characters.
        """
        # Split the document into sections on ## headings
        # Use a regex that captures the heading so we can extract the section name
        raw_sections = re.split(r'\n(?=## )', content)

        all_chunks: list[tuple[str, str]] = []
        current_section = source.replace(".md", "")  # fallback

        for raw in raw_sections:
            raw = raw.strip()
            if not raw:
                continue

            # If this block starts with a heading, parse it as a new section
            heading_match = re.match(r'^(?:#|##)\s+(.+)', raw)
            if heading_match:
                # Extract just the text after ## (skip the title line itself for content)
                heading_text = heading_match.group(1).strip()
                current_section = heading_text

                # Remove the heading line from the body text
                body = re.sub(r'^#+\s+.+\n?', '', raw, count=1).strip()
            else:
                body = raw

            if not body:
                continue

            # Split body into paragraphs (double-newline separated)
            paragraphs = re.split(r'\n\n+', body)
            paragraphs = [p.strip() for p in paragraphs if p.strip()]

            # Merge paragraphs into ~300-500 char chunks
            buf = ""
            for para in paragraphs:
                if not buf:
                    buf = para
                elif len(buf) + len(para) + 2 <= 500:
                    buf += "\n\n" + para
                else:
                    # Current buffer is "full enough" — emit it
                    all_chunks.append((current_section, buf))
                    buf = para

            # Don't forget the last buffer
            if buf:
                all_chunks.append((current_section, buf))

        return all_chunks

    # ── Search ─────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """检索相关文档片段。

        Returns:
            [{"content": "...", "metadata": {...}, "score": 0.92}, ...]
            where score is cosine similarity (0–1, higher = more relevant).
        """
        if self.collection.count() == 0:
            return []

        query_vec = embed(query).tolist()

        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=min(top_k, self.collection.count()),
        )

        docs: list[dict] = []
        if results and results.get("ids") and results["ids"][0]:
            ids_list = results["ids"][0]
            docs_list = results.get("documents", [[]])[0]
            metas_list = results.get("metadatas", [[]])[0]
            dists_list = results.get("distances", [[]])[0]

            for i in range(len(ids_list)):
                content = docs_list[i] if i < len(docs_list) else ""
                metadata = metas_list[i] if i < len(metas_list) else {}
                raw_distance = dists_list[i] if i < len(dists_list) else 2.0

                # Cosine distance → cosine similarity
                # With hnsw:space=cosine, distance = 1 - cos_sim
                # For normalized vectors, cos_sim ∈ [-1, 1], distance ∈ [0, 2]
                score = max(0.0, 1.0 - raw_distance)

                docs.append({
                    "content": content,
                    "metadata": metadata,
                    "score": round(score, 4),
                })

        return docs

    @property
    def chunk_count(self) -> int:
        return self.collection.count()


# ── Singleton ────────────────────────────────────────────────────

_store: KnowledgeStore | None = None


def get_knowledge_store(persist_dir: str | None = None) -> KnowledgeStore:
    """Return the singleton KnowledgeStore instance.

    ChromaDB PersistentClient is designed for long-lived reuse.
    Creating a new client per request can cause file-lock issues.
    """
    global _store
    if _store is None:
        _store = KnowledgeStore(persist_dir=persist_dir)
    return _store
