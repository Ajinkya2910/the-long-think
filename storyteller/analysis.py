"""Turns raw engine + clock + book data into per-move facts.

Every number the UI or the narrative shows is computed here; nothing downstream
invents chess judgements.
"""
from __future__ import annotations

import chess

from .timecontrol import ClockResult
from .wp import move_accuracy, score_to_cp, win_pct

SIDES = ("white", "black")


def line_wp(line: dict) -> float:
    return win_pct(line.get("cp"), line.get("mate"))


def position_eval(analysis: dict) -> dict:
    """White-POV eval of a position from its analysis."""
    if analysis.get("terminal"):
        cp = analysis["cp"]
        mate = 0 if abs(cp) == 10_000 else None
        return {"cp": cp if mate is None else None, "mate": mate, "wp": 100.0 if cp > 0 else 0.0 if cp < 0 else 50.0}
    top = analysis["lines"][0]
    return {"cp": top["cp"], "mate": top["mate"], "wp": round(line_wp(top), 2)}


def mover_wp(wp_white: float, side: int) -> float:
    return wp_white if side == 0 else 100.0 - wp_white


def difficulty(analysis: dict, side: int, window: float, only_gap: float) -> dict:
    """How hard was it to find a good move here?

    * good_moves: engine lines within `window` win% of the best (from multi-PV)
    * gap: win% between best and second-best line
    * only_move: one good move and a big gap
    * score in [0, 1]: half "how few good moves", half "how costly is the 2nd best"
    Forced positions (1 legal move) score 0.
    """
    lines = analysis.get("lines", [])
    legal = analysis.get("legal", len(lines))
    if legal <= 1 or len(lines) < 2:
        return {"score": 0.0, "good_moves": len(lines), "only_move": False, "gap": 0.0, "spread": 0.0, "forced": legal <= 1}
    wps = [mover_wp(line_wp(l), side) for l in lines]
    best = wps[0]
    good = sum(1 for w in wps if best - w <= window)
    gap = best - wps[1]
    spread = best - wps[-1]
    scarcity = 1 - (good - 1) / (len(wps) - 1)
    score = 0.5 * scarcity + 0.5 * min(gap / (2 * only_gap), 1.0)
    return {
        "score": round(score, 3),
        "good_moves": good,
        "only_move": good == 1 and gap >= only_gap,
        "gap": round(gap, 2),
        "spread": round(spread, 2),
        "forced": False,
    }


def classify(wp_loss: float, th: dict) -> str | None:
    if wp_loss >= th["blunder"]:
        return "blunder"
    if wp_loss >= th["mistake"]:
        return "mistake"
    if wp_loss >= th["inaccuracy"]:
        return "inaccuracy"
    return None


def is_obvious(fen_before: str, uci: str, prev_uci: str | None) -> bool:
    """Recaptures and check evasions with few options are "only moves" nobody finds hard."""
    board = chess.Board(fen_before)
    move = chess.Move.from_uci(uci)
    if board.is_check() and board.legal_moves.count() <= 3:
        return True
    if prev_uci and board.is_capture(move) and move.to_square == chess.Move.from_uci(prev_uci).to_square:
        return True
    return False


def phase_of(fen: str, in_book: bool, ply: int, book_known: bool) -> str:
    if in_book or (not book_known and ply < 20):
        return "opening"
    board = chess.Board(fen)
    pieces = sum(
        len(board.pieces(pt, c)) for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN) for c in chess.COLORS
    )
    return "endgame" if pieces <= 6 else "middlegame"


def build_moves(game, analyses: list[dict], clocks: list[ClockResult], opening: dict, cfg) -> list[dict]:
    th = cfg["classification"]
    dc = cfg["difficulty"]
    novelty = opening.get("novelty_ply")
    book_known = opening.get("available", False)
    book_plies = {b["ply"] for b in opening.get("book", [])}
    white, black = game.headers.get("White", "White"), game.headers.get("Black", "Black")
    moves = []
    for ply in range(game.plies):
        side = ply % 2
        before, after = analyses[ply], analyses[ply + 1]
        ev_b, ev_a = position_eval(before), position_eval(after)
        uci = game.ucis[ply]
        lines = before.get("lines", [])
        rank = next((i + 1 for i, l in enumerate(lines) if l["uci"] == uci), None)
        wp_best = mover_wp(line_wp(lines[0]), side) if lines else mover_wp(ev_b["wp"], side)
        wp_after = mover_wp(ev_a["wp"], side)
        wp_loss = 0.0 if rank == 1 else max(0.0, wp_best - wp_after)
        sign = 1 if side == 0 else -1
        best_cp = max(-1000, min(1000, score_to_cp(lines[0]["cp"], lines[0]["mate"]))) if lines else 0
        after_cp = max(-1000, min(1000, score_to_cp(ev_a["cp"], ev_a["mate"])))
        cp_loss = 0 if rank == 1 else max(0, sign * (best_cp - after_cp))
        in_book = ply in book_plies
        clk = clocks[ply]
        diff = difficulty(before, side, float(dc["good_move_window"]), float(dc["only_move_gap"]))
        diff["obvious"] = is_obvious(game.fens[ply], uci, game.ucis[ply - 1] if ply else None)
        if diff["obvious"]:
            diff["score"] = round(diff["score"] * float(dc.get("obvious_discount", 0.25)), 3)
            diff["only_move"] = False
        cls = None if in_book else classify(wp_loss, th)
        tags = []
        if cls:
            tags.append(cls)
        if diff["only_move"]:
            tags.append("only_move" if rank == 1 else "missed_only_move")
        if novelty is not None and ply == novelty:
            tags.append("novelty")
        if "clock_adjustment" in clk.flags:
            tags.append("clock_adjustment")
        moves.append({
            "ply": ply,
            "move_number": ply // 2 + 1,
            "side": SIDES[side],
            "player": white if side == 0 else black,
            "san": game.sans[ply],
            "uci": uci,
            "label": f"{ply // 2 + 1}{'.' if side == 0 else '...'}{game.sans[ply]}",
            "fen_before": game.fens[ply],
            "fen_after": game.fens[ply + 1],
            "clock": {"spent": clk.spent, "remaining": clk.remaining, "adjustment": clk.adjustment, "long_think": False},
            "eval_before": ev_b,
            "eval_after": ev_a,
            "top_lines": [
                {"san": l["san"], "uci": l["uci"], "cp": l["cp"], "mate": l["mate"], "pv_san": l["pv_san"][:6]}
                for l in lines[:3]
            ],
            "played_rank": rank,
            "wp_loss": round(wp_loss, 2),
            "cp_loss": int(cp_loss),
            "accuracy": round(move_accuracy(wp_best, wp_after) if rank != 1 else 100.0, 1),
            "classification": cls,
            "difficulty": diff,
            "in_book": in_book,
            "phase": phase_of(game.fens[ply], in_book, ply, book_known),
            "tags": tags,
        })
    return moves


def flag_long_thinks(moves: list[dict], threshold: int, top_n: int) -> None:
    for side in SIDES:
        mine = [m for m in moves if m["side"] == side and m["clock"]["spent"] is not None]
        top = sorted(mine, key=lambda m: -m["clock"]["spent"])[:top_n]
        top_plies = {m["ply"] for m in top if m["clock"]["spent"] >= 60}
        for m in mine:
            if m["clock"]["spent"] >= threshold or m["ply"] in top_plies:
                m["clock"]["long_think"] = True
                if "long_think" not in m["tags"]:
                    m["tags"].append("long_think")


def score_moment(m: dict, cc: dict) -> dict:
    swing = min(m["wp_loss"] / 20.0, 1.0)
    spent = m["clock"]["spent"] or 0
    tnorm = min(spent / float(cc["time_norm_seconds"]), 1.0)
    diff = m["difficulty"]["score"]
    bonus = float(cc.get("novelty_bonus", 0.0)) if "novelty" in m.get("tags", ()) else 0.0
    total = cc["weight_swing"] * swing + cc["weight_time"] * tnorm + cc["weight_difficulty"] * diff + bonus
    return {"total": round(total, 4), "swing": round(swing, 3), "time": round(tnorm, 3), "difficulty": round(diff, 3), "novelty": bonus}


def rank_critical(moves: list[dict], cc: dict) -> list[dict]:
    """Rank plies by swing + time + difficulty; pick top N at least `min_gap_plies` apart."""
    scored = [(score_moment(m, cc), m) for m in moves]
    scored.sort(key=lambda x: (-x[0]["total"], x[1]["ply"]))
    picked: list[tuple[dict, dict]] = []
    for sc, m in scored:
        if len(picked) >= int(cc["top_n"]):
            break
        if sc["total"] <= 0:
            break
        if any(abs(m["ply"] - p["ply"]) < int(cc["min_gap_plies"]) for _, p in picked):
            continue
        picked.append((sc, m))
    picked.sort(key=lambda x: x[1]["ply"])
    return [{"ply": m["ply"], "score": sc} for sc, m in picked]
