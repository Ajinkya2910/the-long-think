"""Game events built on top of per-move facts.

* reactions     - how long a player thought right after a surprise from the
                  opponent (novelty or classified error), relative to their
                  usual think in that game
* prep_payoff   - evaluation and clocks at the novelty vs N moves later
* missed_chances- opponent errs (hands over >= min_gift win%), and the reply
                  gives a large share of it straight back

Pure functions of the move list, so they work on freshly analysed games and
on game JSON loaded from disk.
"""
from __future__ import annotations

from statistics import median

DEFAULTS = {"prep_payoff_moves": 10, "missed_chance_min_gift": 10.0, "missed_chance_give_back": 0.5}


def _mover_wp(ev: dict, side: str) -> float:
    return ev["wp"] if side == "white" else 100.0 - ev["wp"]


def _mover_pawns(ev: dict, side: str) -> float | None:
    if ev.get("mate") is not None or ev.get("cp") is None:
        return None
    return round((ev["cp"] if side == "white" else -ev["cp"]) / 100, 2)


def usual_think(moves: list[dict], side: str) -> int | None:
    """Median seconds per non-book move for one side (the yardstick for reactions)."""
    vals = [m["clock"]["spent"] for m in moves if m["side"] == side and not m["in_book"] and m["clock"]["spent"] is not None]
    return int(median(vals)) if vals else None


def reactions(moves: list[dict], novelty_ply: int | None) -> list[dict]:
    usual = {s: usual_think(moves, s) for s in ("white", "black")}
    out = []
    for m in moves[:-1]:
        kinds = []
        if novelty_ply is not None and m["ply"] == novelty_ply:
            kinds.append("novelty")
        if m["classification"]:
            kinds.append(m["classification"])
        if not kinds:
            continue
        r = moves[m["ply"] + 1]
        spent, base = r["clock"]["spent"], usual[r["side"]]
        out.append({
            "trigger_ply": m["ply"],
            "trigger_label": m["label"],
            "trigger_kinds": kinds,
            "trigger_side": m["side"],
            "response_ply": r["ply"],
            "response_label": r["label"],
            "response_side": r["side"],
            "spent": spent,
            "usual": base,
            "ratio": round(spent / base, 1) if spent is not None and base else None,
            "response_classification": r["classification"],
        })
    return out


def _clocks_after(moves: list[dict], ply: int, base: int) -> dict:
    c = {"white": base, "black": base}
    for m in moves[: ply + 1]:
        if m["clock"]["remaining"] is not None:
            c[m["side"]] = m["clock"]["remaining"]
    return c


def prep_payoff(moves: list[dict], novelty_ply: int | None, base: int, n_moves: int) -> dict | None:
    """Compare the position and clocks at the novelty with `n_moves` full moves later.

    "At novelty" = position before the novelty move, clocks before it.
    Values are from the point of view of the player who left theory.
    """
    if novelty_ply is None or novelty_ply >= len(moves):
        return None
    nov = moves[novelty_ply]
    side = nov["side"]
    other = "black" if side == "white" else "white"
    end_ply = min(novelty_ply + 2 * n_moves - 1, len(moves) - 1)
    end = moves[end_ply]
    c0 = _clocks_after(moves, novelty_ply - 1, base) if novelty_ply else {"white": base, "black": base}
    c1 = _clocks_after(moves, end_ply, base)
    wp0, wp1 = _mover_wp(nov["eval_before"], side), _mover_wp(end["eval_after"], side)
    return {
        "player_side": side,
        "novelty_ply": novelty_ply,
        "novelty_label": nov["label"],
        "end_ply": end_ply,
        "end_label": end["label"],
        "moves_measured": (end_ply - novelty_ply + 1 + 1) // 2,
        "truncated": end_ply < novelty_ply + 2 * n_moves - 1,
        "eval_before": _mover_pawns(nov["eval_before"], side),
        "eval_after": _mover_pawns(end["eval_after"], side),
        "win_chance_before": round(wp0, 1),
        "win_chance_after": round(wp1, 1),
        "win_chance_change": round(wp1 - wp0, 1),
        "clock_before": {side: c0[side], other: c0[other]},
        "clock_after": {side: c1[side], other: c1[other]},
        # positive = the player who left theory has more time than the opponent
        "clock_gap_before": c0[side] - c0[other],
        "clock_gap_after": c1[side] - c1[other],
    }


def missed_chances(moves: list[dict], min_gift: float, give_back: float) -> list[dict]:
    out = []
    for m in moves[:-1]:
        gift = m["wp_loss"]
        if m["in_book"] or gift < min_gift:
            continue
        r = moves[m["ply"] + 1]
        returned = r["wp_loss"]
        if returned < max(give_back * gift, 0.01):
            continue
        best = r["top_lines"][0] if r["top_lines"] else None
        out.append({
            "error_ply": m["ply"],
            "error_label": m["label"],
            "error_side": m["side"],
            "error_classification": m["classification"],
            "gift": round(gift, 1),
            "reply_ply": r["ply"],
            "reply_label": r["label"],
            "reply_side": r["side"],
            "given_back": round(returned, 1),
            "best_reply": best["san"] if best else None,
            "best_reply_eval": _mover_pawns({"cp": best["cp"], "mate": best["mate"], "wp": 50}, r["side"]) if best else None,
            "reply_spent": r["clock"]["spent"],
        })
    return out


def game_events(doc: dict, pcfg: dict | None = None) -> dict:
    p = {**DEFAULTS, **(pcfg or {})}
    moves = doc["moves"]
    nov = doc["opening"].get("novelty_ply")
    base = doc["time_control"]["periods"][0]["seconds"]
    return {
        "reactions": reactions(moves, nov),
        "usual_think": {s: usual_think(moves, s) for s in ("white", "black")},
        "prep_payoff": prep_payoff(moves, nov, base, int(p["prep_payoff_moves"])),
        "missed_chances": missed_chances(moves, float(p["missed_chance_min_gift"]), float(p["missed_chance_give_back"])),
        "params": p,
    }
