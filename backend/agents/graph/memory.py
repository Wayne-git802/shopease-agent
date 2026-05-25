"""
Global Memory Manager — build + update per-user long-term memory.

Features:
- build(user_id) → UserMemory from DB (purchase history, preferences)
- update(state) → persist preference events with decay
- MemoryDecay: exponential decay τ=90 days
"""
import math
from datetime import datetime

from .state import AgentState, UserMemory, PurchaseSummary, BehavioralProfile


class MemoryDecay:
    """Exponential decay: weight = 1.0 × exp(-Δt / τ)."""
    TAU = 90 * 86400   # 90 days in seconds

    @classmethod
    def decay_weight(cls, event_time: datetime) -> float:
        delta = (datetime.now() - event_time).total_seconds()
        return math.exp(-delta / cls.TAU)

    @classmethod
    def decay_preferences(cls,
                          events: dict[str, list[tuple[float, datetime]]]
                          ) -> dict[str, float]:
        """Decay-weighted preference scores.
        Input:  {category: [(score, timestamp), ...]}
        Output: {category: decayed_average_score}
        """
        result = {}
        for cat, evts in events.items():
            if not evts:
                continue
            total_w = 0.0
            weighted_sum = 0.0
            for score, ts in evts:
                w = cls.decay_weight(ts)
                weighted_sum += score * w
                total_w += w
            result[cat] = weighted_sum / total_w if total_w > 0 else 0.0
        return result


class GlobalMemoryManager:
    """Singleton memory manager."""

    @staticmethod
    def build(user_id: int) -> UserMemory:
        """Build UserMemory from existing DB data."""
        from django.db.models import Avg, Count
        from orders.models import Order
        from products.models import Review, Category

        orders = Order.objects.filter(user_id=user_id)
        total = orders.count()
        avg_value = float(
            orders.aggregate(avg=Avg('total_amount'))['avg'] or 0
        ) if total else 0.0

        top_cats = list(
            Category.objects.filter(
                products__order_items__order__user_id=user_id
            ).annotate(n=Count('id')).order_by('-n').values_list('name', flat=True)[:5]
        )

        last = orders.order_by('-created_at').first()
        last_date = last.created_at if last else None

        purchase = PurchaseSummary(
            total_orders=total,
            avg_order_value=avg_value,
            top_categories=top_cats,
            last_purchase_date=last_date,
        )

        # Behavioral from reviews
        reviews = Review.objects.filter(user_id=user_id)
        total_reviews = reviews.count()
        avg_rating = float(reviews.aggregate(avg=Avg('rating'))['avg'] or 3.0)

        behavioral = BehavioralProfile(
            browse_depth=0.0,
            price_sensitivity=0.5 - (avg_rating - 3.0) * 0.1,
            return_rate=0.0,
            session_frequency="monthly" if total < 3 else "weekly" if total < 10 else "daily",
        )

        # ── Phase B-2: Load preferences from UserPreference distributions ──
        preferences = {}
        try:
            from .feedback.memory_distribution import get_all_preferences, get_best_value
            all_dist = get_all_preferences(user_id)
            for key, dist in all_dist.items():
                best = max(dist, key=dist.get) if dist else None
                if best:
                    # Normalize: map distribution confidence to preference score
                    prefs = sorted(dist.items(), key=lambda x: x[1], reverse=True)
                    top_val, top_weight = prefs[0]
                    # Store the best value with its weight as score
                    preferences[key] = top_weight
        except Exception:
            pass

        return UserMemory(
            user_id=user_id,
            preferences=preferences,
            preference_events={},
            purchase_summary=purchase,
            behavioral_profile=behavioral,
        )

    @staticmethod
    def update(state: AgentState) -> None:
        """After graph execution, update preference events.

        If search or recommend nodes ran, record category preferences
        from the products the user engaged with.
        """
        if not state.user_id or not state.user_memory:
            return
        if not state.retrieved_products and not state.ranked_items:
            return

        import django
        django.setup()

        from products.models import Product, Category
        from django.db import models

        # Products the user saw (top 5 retrieved or ranked)
        seen_ids = {p.id for p in state.retrieved_products[:5]}
        seen_ids |= {r.id for r in state.ranked_items[:5]}

        if not seen_ids:
            return

        # Get categories for seen products
        cat_map = {}
        for p in Product.objects.filter(id__in=seen_ids).select_related('category'):
            if p.category:
                cat_map[p.id] = p.category.name

        now = datetime.now()

        for pid in seen_ids:
            cat = cat_map.get(pid, "其他")
            if cat not in state.user_memory.preference_events:
                state.user_memory.preference_events[cat] = []
            # Score: 1.0 for ranked items (higher engagement), 0.5 for retrieved only
            score = 1.0 if pid in {r.id for r in state.ranked_items} else 0.5
            state.user_memory.preference_events[cat].append((score, now))

        # Apply decay
        state.user_memory.preferences = MemoryDecay.decay_preferences(
            state.user_memory.preference_events
        )
        state.user_memory.updated_at = now


# Singleton
memory_manager = GlobalMemoryManager()
