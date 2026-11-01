"""Interval and test used when comparing retrieval rungs.

eval/score.py has its own copies on purpose: the scorer must not import the system it marks.
"""

import math


def wilson(hits: int, total: int) -> tuple[float, float]:
    """95% Wilson interval for a share."""
    if total == 0:
        return 0.0, 0.0
    z, p = 1.96, hits / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    scale = 1 + z * z / total
    return max(0.0, (centre - spread) / scale), min(1.0, (centre + spread) / scale)


def mcnemar_p(only_a: int, only_b: int) -> float:
    """Exact two-sided McNemar test on the questions where two rungs disagree."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)
