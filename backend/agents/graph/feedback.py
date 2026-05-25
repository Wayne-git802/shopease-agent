"""RLHF Feedback — track user interactions and update preferences."""
import logging
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Action weights for preference update
ACTION_WEIGHTS = {
    'click': 0.5,
    'add_to_cart': 1.0,
    'buy': 3.0,
    'view': 0.2,
}


@dataclass
class FeedbackEvent:
    user_id: int
    product_id: int
    action: str          # 'click' | 'add_to_cart' | 'buy' | 'view'
    category: str = ''
    product_name: str = ''
    timestamp: str = ''


def record_feedback(user_id: int, product_id: int, action: str,
                    category: str = '', product_name: str = '') -> bool:
    """Record a user interaction and update memory preferences.

    Returns True if successfully processed.
    """
    if action not in ACTION_WEIGHTS:
        logger.warning(f"Unknown feedback action: {action}")
        return False

    weight = ACTION_WEIGHTS[action]

    # Update memory preferences
    try:
        from .memory import memory_manager
        from .state import AgentState

        # Build a minimal state to update preferences
        state = AgentState(user_id=user_id, user_query='')
        state.user_memory = memory_manager.build(user_id)

        if state.user_memory and category:
            prefs = state.user_memory.preferences
            if category not in prefs:
                prefs[category] = 0.0
            prefs[category] += weight

            # Record event for decay calculation
            if category not in state.user_memory.preference_events:
                state.user_memory.preference_events[category] = []
            state.user_memory.preference_events[category].append(
                (weight, datetime.now())
            )

            # Update memory
            memory_manager.update(state)
            logger.debug(
                f"Feedback recorded: user={user_id} action={action} "
                f"category={category} weight={weight}"
            )

        return True
    except Exception as e:
        logger.warning(f"Failed to record feedback: {e}")
        return False
