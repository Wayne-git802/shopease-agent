"""
Shared utilities used across graph modules.

Previously duplicated in:
  - search_plan.normalize_query  ≈  preprocessor._normalize
  - reference_resolver._NUM_MAP  ≈  preprocessor._CN_DIGIT
"""
from __future__ import annotations


def normalize_query(query: str) -> str:
    """Fullwidth → halfwidth, strip, lowercase."""
    result = []
    for ch in query:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            result.append(" ")
        else:
            result.append(ch)
    return " ".join("".join(result).split()).lower()


# Chinese digit → integer (shared between ordinal and slot-index parsing)
CN_DIGIT: dict[str, int] = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
