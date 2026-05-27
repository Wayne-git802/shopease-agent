"""
Recommendation Engine — three algorithms for ShopEase AI Agent.

1. Popularity baseline   — top products by review count / average rating
2. Content-based         — same-category recommendations
3. User-based (stub)     — combined popular + content-based

All methods degrade gracefully: return empty list [] if DB tables are
empty or queries fail.  Uses Django ORM directly as a computation module.
"""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RecommendEngine:
    """Recommendation engine providing popularity, content-based, and user
    recommendation strategies."""

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

    # ── cache helper ──────────────────────────────────────────────

    def _cached(self, key, fetcher):
        now = time.time()
        if key in self._cache:
            entry = self._cache[key]
            if now - entry['ts'] < self._cache_ttl:
                return entry['data']
        data = fetcher()
        self._cache[key] = {'data': data, 'ts': now}
        return data

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _product_to_dict(product, reason: str) -> dict:
        """Convert a Product ORM instance to the standard result dict."""
        rating = getattr(product, '_average_rating', None)
        if rating is None:
            rating = 0.0
        else:
            rating = round(float(rating), 1)

        category_name = product.category.name if product.category else ''

        return {
            'product_id': product.id,
            'name': product.name,
            'price': str(product.price),
            'category': category_name,
            'rating': rating,
            'reason': reason,
        }

    # ── algorithm 1: popularity baseline ─────────────────────────

    def get_popular(self, limit: int = 10) -> list[dict]:
        return self._cached(f'popular:{limit}', lambda: self._get_popular_impl(limit))

    def _get_popular_impl(self, limit: int = 10) -> list[dict]:
        """Return top-rated / most-reviewed products.

        Uses review count + average rating from the reviews table via
        the ``ProductQuerySet.with_sales_data()`` annotation.  Falls back
        to newest products when no reviews exist.
        """
        try:
            from products.models import Product

            products = (
                Product.objects.filter(is_active=True)
                .with_sales_data()
                .filter(_review_count__gt=0)
                .order_by('-_review_count', '-_average_rating')
            )[:limit]

            # If no reviewed products yet, return newest active products
            if not products:
                products = (
                    Product.objects.filter(is_active=True)
                    .order_by('-created_at')
                )[:limit]

            return [self._product_to_dict(p, '热门商品') for p in products]
        except Exception as exc:
            logger.warning("get_popular failed: %s", exc)
            return []

    # ── algorithm 2: content-based (same category) ────────────────

    def get_similar(self, product_id: int, limit: int = 5) -> list[dict]:
        """Content-based: products in the same category.

        Excludes the queried product itself.  Returns empty list when the
        product is not found or has no category.
        """
        try:
            from products.models import Product

            try:
                source = Product.objects.select_related('category').get(
                    id=product_id, is_active=True,
                )
            except Product.DoesNotExist:
                return []

            if not source.category:
                return []

            similar = (
                Product.objects.filter(
                    is_active=True,
                    category=source.category,
                )
                .exclude(id=product_id)
                .with_sales_data()
                .order_by('-_review_count', '-_average_rating')
            )[:limit]

            return [self._product_to_dict(p, '同类推荐') for p in similar]
        except Exception as exc:
            logger.warning("get_similar(%s) failed: %s", product_id, exc)
            return []

    # ── algorithm 3: user-based (combined stub) ───────────────────

    def get_for_user(self, user_id: int, limit: int = 10) -> list[dict]:
        """Combined recommendation for a specific user.

        Current strategy (placeholder for collaborative filtering):

        1. Identify categories the user has reviewed positively.
        2. Mix: ~40 % category-matched products + ~60 % popular products.
        3. Fill remaining slots with newest products if needed.
        """
        try:
            from products.models import Product, Review

            # ── discover user's preferred categories ──────────────
            user_category_ids: set[int] = set()
            try:
                reviewed_cats = (
                    Review.objects.filter(
                        user_id=user_id,
                        status='visible',
                        rating__gte=4,
                    )
                    .select_related('product__category')
                    .values_list('product__category_id', flat=True)
                    .distinct()
                )
                user_category_ids = {cid for cid in reviewed_cats if cid is not None}
            except Exception:
                pass

            results: list[dict] = []
            seen_ids: set[int] = set()

            # ── 40 % from user preferences ────────────────────────
            if user_category_ids:
                slot = max(1, int(limit * 0.4))
                qs = (
                    Product.objects.filter(
                        is_active=True,
                        category_id__in=user_category_ids,
                    )
                    .with_sales_data()
                    .order_by('-_review_count', '-_average_rating')
                )
                for p in qs:
                    if len(results) >= slot:
                        break
                    if p.id not in seen_ids:
                        seen_ids.add(p.id)
                        results.append(
                            self._product_to_dict(p, '根据你的喜好推荐')
                        )

            # ── 60 % popular products ─────────────────────────────
            popular_slot = limit - len(results)
            if popular_slot > 0:
                qs = (
                    Product.objects.filter(is_active=True)
                    .with_sales_data()
                    .filter(_review_count__gt=0)
                    .order_by('-_review_count', '-_average_rating')
                )
                for p in qs:
                    if len(results) >= limit:
                        break
                    if p.id not in seen_ids:
                        seen_ids.add(p.id)
                        results.append(self._product_to_dict(p, '热门商品'))

            # ── fallback: newest ──────────────────────────────────
            if len(results) < limit:
                fallback_slot = limit - len(results)
                qs = (
                    Product.objects.filter(is_active=True)
                    .exclude(id__in=seen_ids)
                    .order_by('-created_at')
                )[:fallback_slot]
                for p in qs:
                    results.append(self._product_to_dict(p, '新品推荐'))

            return results[:limit]
        except Exception as exc:
            logger.warning("get_for_user(%s) failed: %s", user_id, exc)
            return []

    # ── alias ────────────────────────────────────────────────────

    def get_trending(self, limit: int = 10) -> list[dict]:
        """Alias for ``get_popular``."""
        return self.get_popular(limit)

    # ── scored: full fusion pipeline ────────────────────────────

    def get_scored(
        self,
        user_id: int | None = None,
        strategy: str = "popular",
        limit: int = 8,
    ) -> list[tuple[Any, float, dict[str, str]]]:
        """Return top-N products with fused scores + structured explains.

        Uses strategy_router + score_fusion for three-track scoring.

        Args:
            user_id: user id or None for anonymous.
            strategy: "popular" | "cold_start" | "personalized" | "hybrid".
            limit: max results.

        Returns:
            [(product_orm, final_score, explain_dict), ...] sorted by score desc.
        """
        from agents.commerce.score_fusion import fuse
        from products.models import Product

        # ── fetch candidate pool ──────────────────────────────
        if strategy == "popular":
            candidates = Product.objects.filter(is_active=True).with_sales_data()[:50]
        elif strategy == "cold_start":
            popular = set(
                Product.objects.filter(is_active=True)
                .with_sales_data()
                .filter(_review_count__gt=0)
                .order_by('-_review_count')
                .values_list('id', flat=True)[:30]
            )
            newest = set(
                Product.objects.filter(is_active=True)
                .order_by('-created_at')
                .values_list('id', flat=True)[:20]
            )
            all_ids = list(dict.fromkeys(list(popular) + list(newest)))
            candidates = Product.objects.filter(id__in=all_ids).with_sales_data()
        else:
            candidates = Product.objects.filter(is_active=True).with_sales_data()[:60]

        # ── score & rank ──────────────────────────────────────
        scored = []
        for p in candidates:
            final, explain = fuse(p, user_id, strategy)
            scored.append((p, final, explain))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]
