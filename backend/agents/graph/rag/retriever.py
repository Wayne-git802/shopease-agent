"""
Retriever — hybrid search (FAISS vector + SQL keyword → RRF fusion).

Implements RetrieverProtocol from contracts/rag_protocol.py.
"""
import numpy as np

from ..state import ProductRef, DocRef
from ..contracts.rag_protocol import RetrieverProtocol
from .embedder import embed, embed_batch
from .vector_store import get_store


class Retriever(RetrieverProtocol):
    """Hybrid retriever: FAISS + MySQL LIKE → RRF fusion."""

    VECTOR_WEIGHT = 0.7
    KEYWORD_WEIGHT = 0.3
    RRF_K = 60                    # RRF constant

    def search(self, query: str, top_k: int = 10,
               user_id: int | None = None) -> tuple[list[ProductRef], list[DocRef]]:
        # ── Ensure index is built ──
        store = get_store()
        if store.index is None:
            self._build_index_from_db()

        # ── Vector search ──
        q_vec = embed(query)
        vec_results = store.search(q_vec, k=top_k * 3)  # over-fetch for fusion

        # ── Keyword search (MySQL LIKE) ──
        kw_results = self._keyword_search(query, top_k * 3)

        # ── RRF fusion ──
        fused = self._rrf_fuse(vec_results, kw_results, top_k)

        # ── Build ProductRef from DB ──
        products = self._fetch_products(fused)
        docs: list[DocRef] = []   # no document store yet

        return products, docs

    def embed(self, text: str) -> np.ndarray:
        return embed(text)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return embed_batch(texts)

    def index_products(self, product_texts: list[tuple[int, str]]) -> None:
        """Build FAISS index from [(product_id, text), ...]"""
        ids = [pid for pid, _ in product_texts]
        texts = [t for _, t in product_texts]
        vectors = embed_batch(texts)
        get_store().build(ids, vectors)

    def save_index(self, path: str) -> None:
        get_store().save(path)

    def load_index(self, path: str) -> None:
        get_store().load(path)

    # ── Internals ─────────────────────────────────────────────

    def _build_index_from_db(self) -> None:
        """Auto-build FAISS index from active products in DB."""
        import django
        django.setup()
        from products.models import Product

        products = Product.objects.filter(is_active=True).values_list('id', 'name')
        ids = [pid for pid, _ in products]
        texts = [name for _, name in products]
        if ids:
            vectors = embed_batch(texts)
            get_store().build(ids, vectors)

    def _keyword_search(self, query: str, limit: int = 30) -> list[tuple[int, float]]:
        """MySQL LIKE on product name/description. Returns [(product_id, score), ...]"""
        import django
        django.setup()
        from products.models import Product
        from django.db.models import Q

        words = query.split()
        q_filter = Q()
        for w in words:
            q_filter |= Q(name__icontains=w) | Q(description__icontains=w)

        products = Product.objects.filter(q_filter, is_active=True)[:limit]
        # Score = 1.0 for exact name match, 0.5 for partial
        results = []
        for p in products:
            name_lower = p.name.lower()
            query_lower = query.lower()
            if query_lower in name_lower:
                score = 1.0
            elif any(w.lower() in name_lower for w in words):
                score = 0.7
            else:
                score = 0.5
            results.append((p.id, score))
        return results

    @staticmethod
    def _rrf_fuse(vec: list[tuple[int, float]],
                  kw: list[tuple[int, float]],
                  top_k: int) -> list[tuple[int, float]]:
        """Reciprocal Rank Fusion: rrf_score = Σ 1/(k + rank)"""
        RRF_K = 60
        scores: dict[int, float] = {}

        for rank, (pid, _) in enumerate(vec):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank + 1)
        for rank, (pid, _) in enumerate(kw):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank + 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _fetch_products(fused: list[tuple[int, float]]) -> list[ProductRef]:
        """Build ProductRef from DB for the fused product IDs."""
        if not fused:
            return []

        import django
        django.setup()
        from products.models import Product

        score_map = dict(fused)
        ids = [pid for pid, _ in fused]
        db_products = Product.objects.filter(id__in=ids, is_active=True)

        refs = []
        for p in db_products:
            refs.append(ProductRef(
                id=p.id,
                name=p.name,
                price=float(p.price),
                category=p.category.name if p.category else "",
                relevance=score_map.get(p.id, 0.0),
            ))
        # Sort by relevance descending
        refs.sort(key=lambda r: r.relevance, reverse=True)
        return refs


# ── Singleton ────────────────────────────────────────────────────

_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
