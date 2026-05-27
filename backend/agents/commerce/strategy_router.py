"""Strategy Router — decides which recommendation strategy to use.

Returns (strategy, reason) for Console observability.
The interface accepts any callable — probabilistic routing is a drop-in replacement.
"""


def has_purchases(user_id: int) -> bool:
    """Check if user has any completed orders."""
    from orders.models import Order
    return Order.objects.filter(user_id=user_id).exists()


def has_signals(user_id: int) -> bool:
    """Check if user has any INTENT or CONVERSION signals."""
    from agents.graph.feedback.signal_store import signal_count
    return signal_count(user_id) > 0


def route(user) -> tuple[str, str]:
    """Returns (strategy, reason).

    Strategies:
        popular       — anonymous user, pure popularity ranking
        cold_start    — logged in but no purchase history
        personalized  — has purchases + behavioral signals
        hybrid        — has purchases but no signals yet
    """
    if user is None or not user.is_authenticated:
        return "popular", "anonymous_user"
    if not has_purchases(user.id):
        return "cold_start", "no_purchase_history"
    if has_signals(user.id):
        return "personalized", "has_purchase_and_signals"
    return "hybrid", "has_purchase_no_signals"
