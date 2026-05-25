"""
Signal Contract — defines SignalType enum and associated reward weights.

All downstream consumers (ranking feedback, memory distribution, routing tuning)
import from here. This is the SSOT for signal semantics.
"""

from enum import StrEnum


class SignalType(StrEnum):
    """Semantic classification of user behavior signals.

    Not all user actions mean the same thing:
      - click  = curiosity (exploration) — does NOT mean preference
      - add_cart = intent — partially indicates preference
      - purchase  = conversion — strong preference signal
      - dismiss   = negative — mild negative signal
      - clarify   = stated preference — explicit user declaration
    """
    EXPLORATION = "exploration"   # click, dwell — diversity only
    INTENT = "intent"             # add_cart — ranking (×0.4)
    CONVERSION = "conversion"     # purchase — memory + ranking full weight
    NEGATIVE = "negative"         # dismiss — ranking penalty
    STATED = "stated"             # clarify answer — memory distribution


# Reward weights for ranking feedback.
# EXPLORATION and STATED have zero ranking impact — they flow to
# diversity boosting and memory distribution respectively.
SIGNAL_WEIGHTS: dict[SignalType, float] = {
    SignalType.EXPLORATION:  0.00,
    SignalType.INTENT:       0.04,   # light ranking boost
    SignalType.CONVERSION:   0.10,   # full ranking boost
    SignalType.NEGATIVE:    -0.02,   # light ranking penalty
    SignalType.STATED:       0.00,   # no ranking impact (goes to memory)
}
