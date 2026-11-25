"""Pattern finder: per-game summaries and cross-game player profiles.

All statistics are plain aggregates of per-move facts; the insight sentences
are generated from those numbers with fixed thresholds.
"""
from __future__ import annotations

from statistics import mean

from .narrative import fmt_dur

CLOCK_BUCKETS = [("> 60 min", 3600, 10**9), ("30–60 min", 1800, 3600), ("10–30 min", 600, 1800), ("< 10 min", 0, 600)]
THINK_BUCKETS = [("< 1 min", 0, 60), ("1–5 min", 60, 300), ("5–15 min", 300, 900), ("> 15 min", 900, 10**9)]
PHASES = ("opening", "middlegame", "endgame")


def _clock_before(moves: list[dict], m: dict, base: int) -> int | None:
    prev = [x for x in moves[: m["ply"]] if x["side"] == m["side"]]
    return prev[-1]["clock"]["remaining"] if prev else base


def _bucket(rows: list[tuple[float, float]], buckets) -> list[dict]:
    out = []
    for name, lo, hi in buckets:
        vals = [acc for key, acc in rows if key is not None and lo <= key < hi]
        out.append({"bucket": name, "moves": len(vals), "accuracy": round(mean(vals), 1) if vals else None})
    return out


def player_game_stats(doc: dict, side: str) -> dict:
    moves = doc["moves"]
    base = doc["time_control"]["periods"][0]["seconds"]
    mine = [m for m in moves if m["side"] == side]
    out_book = [m for m in mine if not m["in_book"]]
    spent = [m["clock"]["spent"] or 0 for m in mine]
    longest = max(mine, key=lambda m: m["clock"]["spent"] or 0) if mine else None
    phase_time = {p: sum(m["clock"]["spent"] or 0 for m in mine if m["phase"] == p) for p in PHASES}
    nov = doc["opening"].get("novelty_ply")
    before_nov = sum(m["clock"]["spent"] or 0 for m in mine if nov is not None and m["ply"] < nov)
    # moves 31–40 played with < 5 min left = time trouble before the control
    trouble = [m for m in mine if 30 < m["move_number"] <= 40 and (m["clock"]["remaining"] or 10**9) < 300]
    return {
        "name": doc["players"][side]["name"],
        "color": side,
        "moves": len(mine),
        "accuracy": round(mean(m["accuracy"] for m in out_book), 1) if out_book else None,
        "acpl": round(mean(m["cp_loss"] for m in out_book)) if out_book else None,
        "inaccuracies": sum(m["classification"] == "inaccuracy" for m in mine),
        "mistakes": sum(m["classification"] == "mistake" for m in mine),
        "blunders": sum(m["classification"] == "blunder" for m in mine),
        "time_used": sum(spent),
        "time_by_phase": phase_time,
        "time_before_novelty": before_nov if nov is not None else None,
        "longest_think": {"ply": longest["ply"], "label": longest["label"], "seconds": longest["clock"]["spent"]} if longest else None,
        "long_thinks": sum(m["clock"]["long_think"] for m in mine),
        "time_trouble_moves": len(trouble),
        "final_clock": mine[-1]["clock"]["remaining"] if mine else None,
        "_rows": [
            {
                "clock_before": _clock_before(moves, m, base),
                "spent": m["clock"]["spent"],
                "accuracy": m["accuracy"],
                "difficulty": m["difficulty"]["score"],
                "phase": m["phase"],
            }
            for m in out_book
        ],
    }


def game_summary(doc: dict) -> dict:
    nov = doc["opening"].get("novelty_ply")
    novelty = None
    if nov is not None and nov < len(doc["moves"]):
        m = doc["moves"][nov]
        novelty = {"ply": nov, "label": m["label"], "player": m["player"], "side": m["side"]}
    players = {s: player_game_stats(doc, s) for s in ("white", "black")}
    longest = max((p["longest_think"] for p in players.values() if p["longest_think"]), key=lambda t: t["seconds"] or 0, default=None)
    return {
        "novelty": novelty,
        "longest_think": longest,
        "critical_count": len(doc["critical_moments"]),
        "players": {s: {k: v for k, v in p.items() if k != "_rows"} for s, p in players.items()},
        "_rows": {s: p["_rows"] for s, p in players.items()},
    }


def move_rows(docs: list[dict]) -> list[list]:
    """Flat per-move table for the cross-game moves map (compact arrays)."""
    rows = []
    for doc in docs:
        base = doc["time_control"]["periods"][0]["seconds"]
        for m in doc["moves"]:
            rows.append([
                doc["id"], m["ply"], m["label"], m["player"], m["side"], m["clock"]["spent"],
                m["wp_loss"], m["accuracy"], m["phase"], m["difficulty"]["score"],
                _clock_before(doc["moves"], m, base), m["in_book"], m["classification"],
            ])
    return rows


MOVE_COLUMNS = ["game", "ply", "label", "player", "side", "spent", "wp_loss", "accuracy", "phase", "difficulty", "clock_before", "in_book", "classification"]


def match_patterns(docs: list[dict], display: dict) -> dict:
    """Aggregate per player (by name) across all analysed games."""
    profiles: dict[str, dict] = {}
    for doc in docs:
        summ = doc["summary"]
        for side in ("white", "black"):
            name = doc["players"][side]["name"]
            pr = profiles.setdefault(name, {"name": name, "games": 0, "points": 0.0, "rows": [], "per_game": [], "time_by_phase": {p: 0 for p in PHASES}, "novelties_played": 0, "time_before_novelty": []})
            ps = summ["players"][side]
            pr["games"] += 1
            res = doc["result"]
            pr["points"] += {"1-0": 1.0 if side == "white" else 0.0, "0-1": 1.0 if side == "black" else 0.0, "1/2-1/2": 0.5}.get(res, 0.0)
            pr["rows"] += summ["_rows"][side]
            for p in PHASES:
                pr["time_by_phase"][p] += ps["time_by_phase"][p]
            if summ["novelty"] and summ["novelty"]["side"] == side:
                pr["novelties_played"] += 1
            if ps["time_before_novelty"] is not None:
                pr["time_before_novelty"].append(ps["time_before_novelty"])
            pr["per_game"].append({"game_id": doc["id"], "color": side, "accuracy": ps["accuracy"], "acpl": ps["acpl"], "time_used": ps["time_used"], "longest_think": ps["longest_think"], "time_trouble_moves": ps["time_trouble_moves"]})

    out = {}
    for name, pr in profiles.items():
        rows = pr["rows"]
        accs = [r["accuracy"] for r in rows]
        total_time = sum(pr["time_by_phase"].values()) or 1
        hard = [r["accuracy"] for r in rows if r["difficulty"] >= 0.5]
        easy = [r["accuracy"] for r in rows if r["difficulty"] < 0.5]
        out[name] = {
            "name": name,
            "short": display.get(name, {}).get("short", name),
            "slot": display.get(name, {}).get("slot", 1),
            "games": pr["games"],
            "points": pr["points"],
            "accuracy": round(mean(accs), 1) if accs else None,
            "time_share_by_phase": {p: round(100 * v / total_time, 1) for p, v in pr["time_by_phase"].items()},
            "time_by_phase": pr["time_by_phase"],
            "accuracy_by_clock": _bucket([(r["clock_before"], r["accuracy"]) for r in rows], CLOCK_BUCKETS),
            "accuracy_by_think": _bucket([(r["spent"], r["accuracy"]) for r in rows], THINK_BUCKETS),
            "accuracy_hard": {"moves": len(hard), "accuracy": round(mean(hard), 1) if hard else None},
            "accuracy_easy": {"moves": len(easy), "accuracy": round(mean(easy), 1) if easy else None},
            "novelties_played": pr["novelties_played"],
            "avg_time_before_novelty": round(mean(pr["time_before_novelty"])) if pr["time_before_novelty"] else None,
            "per_game": pr["per_game"],
        }
    return {"players": out, "insights": insights(out, docs), "move_columns": MOVE_COLUMNS, "moves": move_rows(docs)}


def insights(players: dict, docs: list[dict]) -> list[dict]:
    """Fact-backed one-liners. Each carries the numbers it is based on."""
    out = []
    for p in players.values():
        n = p["short"]
        sh = p["time_share_by_phase"]
        top_phase = max(sh, key=sh.get)
        out.append({"player": p["name"], "kind": "time_budget", "text": f"{sh[top_phase]:.0f}% of {n}'s thinking time went into the {top_phase}.", "evidence": sh})
        clock = [b for b in p["accuracy_by_clock"] if b["moves"] >= 3]
        if len(clock) >= 2:
            hi, lo = clock[0], clock[-1]
            if hi["accuracy"] is not None and lo["accuracy"] is not None and abs(hi["accuracy"] - lo["accuracy"]) >= 3:
                word = "dropped" if lo["accuracy"] < hi["accuracy"] else "rose"
                out.append({"player": p["name"], "kind": "time_pressure", "text": f"{n}'s accuracy {word} from {hi['accuracy']:.0f}% with {hi['bucket']} on the clock to {lo['accuracy']:.0f}% with {lo['bucket']}.", "evidence": clock})
        thinks = [b for b in p["accuracy_by_think"] if b["moves"] >= 2]
        long_b = next((b for b in thinks if b["bucket"] == "> 15 min"), None)
        quick_b = next((b for b in thinks if b["bucket"] == "< 1 min"), None)
        if long_b and quick_b:
            out.append({"player": p["name"], "kind": "long_thinks", "text": f"After thinks of over 15 minutes, {n} averaged {long_b['accuracy']:.0f}% accuracy (vs {quick_b['accuracy']:.0f}% on moves under a minute).", "evidence": thinks})
        if p["accuracy_hard"]["moves"] >= 3 and p["accuracy_easy"]["moves"] >= 3:
            out.append({"player": p["name"], "kind": "difficulty", "text": f"In positions with few good options, {n} scored {p['accuracy_hard']['accuracy']:.0f}% accuracy, vs {p['accuracy_easy']['accuracy']:.0f}% in easier positions.", "evidence": {"hard": p["accuracy_hard"], "easy": p["accuracy_easy"]}})
        if p["avg_time_before_novelty"] is not None:
            out.append({"player": p["name"], "kind": "prep", "text": f"{n} used on average {fmt_dur(p['avg_time_before_novelty'])} before the game left known theory.", "evidence": {"avg_seconds": p["avg_time_before_novelty"], "games": p["games"]}})
    return out
