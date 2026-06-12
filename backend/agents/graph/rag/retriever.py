"""
Retriever — hybrid search (FAISS vector + SQL keyword → RRF fusion).

Implements RetrieverProtocol from contracts/rag_protocol.py.
"""
import numpy as np

from ..state import ProductRef, DocRef
from ..contracts.rag_protocol import RetrieverProtocol
from .embedder import embed, embed_batch
from .vector_store import get_store, VectorStore


def _ensure_django():
    """Lazy Django setup — call once, idempotent."""
    import django
    django.setup()


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

        # ── Build review index if not already on disk ──
        import os as _os
        if not _os.path.exists('faiss_index/reviews.index'):
            self._build_review_index()

        # ── Vector search ──
        q_vec = embed(query)
        vec_results = store.search(q_vec, k=top_k * 3)  # over-fetch for fusion

        # ── Keyword search (MySQL LIKE) ──
        kw_results = self._keyword_search(query, top_k * 3)

        # ── RRF fusion ──
        fused = self._rrf_fuse(vec_results, kw_results, top_k)

        # ── Build ProductRef from DB ──
        products = self._fetch_products(fused)

        # ── Review search ──
        review_scores = self._review_search(q_vec, top_k=200)
        for p in products:
            p.review_score = review_scores.get(p.id, 0.0)

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
        _ensure_django()
        from products.models import Product
        from agents.commerce.queries.product_query import ProductQuery

        products = ProductQuery.purchasable().select_related('category').filter(
            brand__isnull=False
        ).values_list(
            'id', 'name', 'description', 'specs', 'category__name'
        )[:500]
        ids = []
        texts = []
        for pid, name, desc, specs, cat_name in products:
            ids.append(pid)
            specs = specs or {}
            use_case = specs.get('use_case', '')
            cat_name = cat_name or ''
            desc = desc or ''

            pros_list = specs.get('pros', [])
            if isinstance(pros_list, str):
                pros_list = [p.strip() for p in pros_list.split(',') if p.strip()]
            cons_list = specs.get('cons', [])
            if isinstance(cons_list, str):
                cons_list = [c.strip() for c in cons_list.split(',') if c.strip()]
            pros_str = ' '.join(pros_list) if pros_list else ''
            cons_str = ' '.join(cons_list) if cons_list else ''
            text = f"{name} | 场景:{use_case} | {desc} | 优点:{pros_str} | 缺点:{cons_str}"
            texts.append(text)
        if ids:
            vectors = embed_batch(texts)
            get_store().build(ids, vectors)

    def _build_review_index(self) -> None:
        """Build FAISS index from mean-pooled review embeddings."""
        _ensure_django()
        from products.models import Product
        from agents.commerce.queries.product_query import ProductQuery

        products = ProductQuery.purchasable().filter(brand__isnull=False).values_list('id', 'specs')[:500]
        ids = []
        review_vecs = []
        for pid, specs in products:
            specs = specs or {}
            reviews = specs.get('review_text', [])
            if isinstance(reviews, str):
                reviews = [reviews]
            if reviews:
                vecs = embed_batch(reviews)  # shape: (N, dim)
                mean_vec = vecs.mean(axis=0)  # mean pool
            else:
                mean_vec = np.zeros(384, dtype=np.float32)  # 0 vector for no reviews

            ids.append(pid)
            review_vecs.append(mean_vec)

        if ids:
            review_store = VectorStore()
            review_store.build(ids, np.array(review_vecs))
            review_store.save('faiss_index/reviews.index')

    def _review_search(self, query_vec: np.ndarray, top_k: int = 200) -> dict[int, float]:
        """Search review index, return {product_id: review_similarity}"""
        review_store = VectorStore()
        loaded = review_store.load('faiss_index/reviews.index')

        if not loaded or review_store.index is None or review_store.index.ntotal == 0:
            return {}

        distances, indices = review_store.index.search(query_vec.reshape(1, -1), min(top_k, review_store.index.ntotal))

        scores = {}
        for dist, idx in zip(distances[0], indices[0]):
            if 0 <= idx < len(review_store.id_map):
                pid = review_store.id_map[idx]
                scores[pid] = float(1.0 - dist) if dist < 10 else 0.0
        return scores

    def _keyword_search(self, query: str, limit: int = 30) -> list[tuple[int, float]]:
        """MySQL LIKE on product name/description. Returns [(product_id, score), ...]"""
        _ensure_django()
        from products.models import Product
        from django.db.models import Q
        from agents.commerce.queries.product_query import ProductQuery

        words = query.split()
        q_filter = Q()
        for w in words:
            q_filter |= Q(name__icontains=w) | Q(description__icontains=w)

        products = ProductQuery.purchasable().filter(q_filter, brand__isnull=False)[:limit]
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
        scores: dict[int, float] = {}

        for rank, (pid, _) in enumerate(vec):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (Retriever.RRF_K + rank + 1)
        for rank, (pid, _) in enumerate(kw):
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (Retriever.RRF_K + rank + 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _fetch_products(fused: list[tuple[int, float]]) -> list[ProductRef]:
        """Build ProductRef from DB for the fused product IDs."""
        if not fused:
            return []

        _ensure_django()
        from products.models import Product
        from agents.commerce.queries.product_query import ProductQuery

        score_map = dict(fused)
        ids = [pid for pid, _ in fused]
        db_products = ProductQuery.purchasable().filter(id__in=ids)

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
