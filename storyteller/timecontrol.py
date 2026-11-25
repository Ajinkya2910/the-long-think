"""Time-control parsing and per-move clock math.

Clock semantics (DGT / Lichess broadcast %clk):
  * %clk is the mover's remaining time right *after* pressing the clock,
    i.e. it already includes any increment and any period bonus earned by
    that move.
  * spent(move n) = clock_before - clock_after + increment(n) + bonus(n)
  * A negative result means time was *added* outside the rules (arbiter time
    award, clock correction). We report that as an adjustment instead of a
    negative think.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Period:
    moves: int | None  # None = rest of the game
    seconds: int


@dataclass(frozen=True)
class TimeControl:
    periods: tuple[Period, ...]
    increment: int = 0
    increment_from_move: int = 1

    @property
    def base(self) -> int:
        return self.periods[0].seconds

    def increment_for(self, move_number: int) -> int:
        return self.increment if move_number >= self.increment_from_move else 0

    def bonus_after(self, move_number: int) -> int:
        """Seconds added to the clock when the player completes `move_number`."""
        boundary = 0
        for i, p in enumerate(self.periods[:-1]):
            if p.moves is None:
                break
            boundary += p.moves
            if move_number == boundary:
                return self.periods[i + 1].seconds
        return 0

    def describe(self) -> str:
        parts = []
        for p in self.periods:
            mins = p.seconds // 60
            parts.append(f"{mins}′/{p.moves} moves" if p.moves else f"{mins}′ rest")
        s = " + ".join(parts)
        if self.increment:
            s += f", +{self.increment}″/move from move {self.increment_from_move}"
        return s

    def to_dict(self) -> dict:
        return {
            "periods": [{"moves": p.moves, "seconds": p.seconds} for p in self.periods],
            "increment": self.increment,
            "increment_from_move": self.increment_from_move,
            "description": self.describe(),
        }


def from_config(tc: dict) -> TimeControl:
    periods = tuple(Period(p.get("moves"), int(p["seconds"])) for p in tc["periods"])
    return TimeControl(periods, int(tc.get("increment", 0)), int(tc.get("increment_from_move", 1)))


_PGN_PERIOD = re.compile(r"^(?:(\d+)/)?(\d+)(?:\+(\d+))?$")


def parse_pgn_header(header: str) -> TimeControl | None:
    """Parse the PGN-standard TimeControl tag, e.g. '40/7200:1800+30'.

    Per the PGN spec an increment written on the last period applies from the
    start of that period. Returns None for anything non-standard (e.g. the
    free-text FIDE description some broadcasts use).
    """
    if not header or header in ("?", "-"):
        return None
    periods: list[Period] = []
    increment, inc_from = 0, 1
    moves_so_far = 0
    for chunk in header.split(":"):
        m = _PGN_PERIOD.match(chunk.strip())
        if not m:
            return None
        moves = int(m.group(1)) if m.group(1) else None
        periods.append(Period(moves, int(m.group(2))))
        if m.group(3):
            increment = int(m.group(3))
            inc_from = moves_so_far + 1
        if moves:
            moves_so_far += moves
    return TimeControl(tuple(periods), increment, inc_from)


@dataclass
class ClockResult:
    spent: int | None          # seconds thought on this move (None if unknown)
    remaining: int | None      # clock after the move
    adjustment: int = 0        # seconds added outside the rules (arbiter award / correction)
    flags: list[str] = field(default_factory=list)


def compute_spent(
    clocks: list[int | None], tc: TimeControl
) -> list[ClockResult]:
    """`clocks[i]` is the %clk after ply i (ply 0 = White's first move).

    Returns one ClockResult per ply.
    """
    out: list[ClockResult] = []
    prev = {0: tc.base, 1: tc.base}  # 0 = white, 1 = black
    for ply, clk in enumerate(clocks):
        side = ply % 2
        move_no = ply // 2 + 1
        if clk is None or prev[side] is None:
            out.append(ClockResult(None, clk, flags=["missing_clock"]))
            prev[side] = clk
            continue
        gained = tc.increment_for(move_no) + tc.bonus_after(move_no)
        spent = prev[side] - clk + gained
        res = ClockResult(spent, clk)
        if spent < 0:
            # Clock went up by more than the rules allow.
            res.adjustment = -spent
            res.spent = None
            res.flags.append("clock_adjustment")
        out.append(res)
        prev[side] = clk
    return out
