"""Win-probability helpers (Lichess's published model)."""
from __future__ import annotations

import math

MATE_CP = 10_000


def score_to_cp(cp: int | None, mate: int | None) -> int:
    if mate is not None:
        return MATE_CP - abs(mate) * 10 if mate > 0 else -MATE_CP + abs(mate) * 10
    return int(cp or 0)


def win_pct(cp: int | None, mate: int | None = None) -> float:
    """White's winning chance in % (0..100) from White-POV cp / mate."""
    if mate is not None:
        return 100.0 if mate > 0 else 0.0
    c = max(-1000, min(1000, cp or 0))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * c)) - 1)


def move_accuracy(wp_before: float, wp_after: float) -> float:
    """Lichess move accuracy from the mover's win% before/after the move."""
    diff = max(0.0, wp_before - wp_after)
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * diff) - 3.1669))
