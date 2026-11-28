"""Plain-language headlines for charts and game cards, from fixed rules.

These sit above charts on the home page, so they must stay true after every
game. They are computed here from the numbers, never written by a model, and
fall back to a neutral description when the data is too thin to say more.
"""
from __future__ import annotations

from .narrative import fmt_dur

MIN_N = 3          # fewer moves than this in a bucket: don't draw a conclusion
SMALL_N = 10       # the site marks buckets below this as a small sample


def _short(p: dict) -> str:
    return p.get("short") or p["name"].split(",")[0]


def lowest_clock_before_40(doc: dict) -> dict | None:
    """Lowest clock (before the move-40 bonus) over both players: {side, seconds, label}."""
    best = None
    for m in doc["moves"]:
        r = m["clock"].get("remaining")
        if m["move_number"] <= 39 and r is not None and (best is None or r < best["seconds"]):
            best = {"side": m["side"], "seconds": r, "label": m["label"], "ply": m["ply"]}
    return best


def game_tag(doc: dict) -> str:
    """One short fact that sums up a game, for its card on the home page."""
    p = doc["players"]
    if doc["result"] in ("1-0", "0-1"):
        return f"{_short(p['white' if doc['result'] == '1-0' else 'black'])} won"
    low = lowest_clock_before_40(doc)
    if low and low["seconds"] < 60:
        return f"{_short(p[low['side']])} down to {low['seconds']} seconds"
    lt = doc["summary"].get("longest_think")
    if lt and lt["seconds"] >= 30 * 60:
        side = doc["moves"][lt["ply"]]["side"]
        return f"{_short(p[side])} thought {lt['seconds'] // 60} min on one move"
    moves = doc["moves"][-1]["move_number"]
    if moves < 30:
        return f"{'Drawn' if doc['result'] == '1/2-1/2' else 'Over'} in {moves} moves"
    nov = doc["summary"].get("novelty")
    return f"Prep ended at {nov['label']}" if nov else f"{moves} moves"


def _trend(vals: list[float]) -> int:
    """+1 rising every game, -1 falling every game, 0 otherwise (needs 3+ values)."""
    if len(vals) < 3:
        return 0
    steps = {(b > a) - (b < a) for a, b in zip(vals, vals[1:])}
    return steps.pop() if len(steps) == 1 and 0 not in steps else 0


def prep_headline(series: dict[str, list[float]]) -> str:
    """series: {short name: [seconds before leaving theory, per game]}."""
    t = {n: _trend(v) for n, v in series.items()}
    names = list(series)
    if len(names) == 2 and t[names[0]] and t[names[1]] and t[names[0]] != t[names[1]]:
        return "Prep time is moving in opposite directions"
    for n in names:
        if t[n] < 0:
            return f"{n} is leaving theory faster every game"
        if t[n] > 0:
            return f"{n} is taking longer to leave theory every game"
    return "Time used before leaving known theory, game by game"


def _bucket(rows: list[dict], name: str) -> dict | None:
    return next((r for r in rows if r["bucket"] == name), None)


def chart_headlines(players: dict) -> dict:
    """players: patterns['players'] keyed by full name. Returns {chart: headline}."""
    P = [p for p in players.values() if p.get("games")]
    out = {}
    if len(P) != 2:
        return out
    a, b = P
    sa, sb = a["short"], b["short"]

    # time budget
    top = {p["short"]: max(p["time_share_by_phase"], key=p["time_share_by_phase"].get) for p in P}
    out["phase"] = (f"Both players spend most of their time in the {top[sa]}" if top[sa] == top[sb]
                    else f"{sa} spends most time in the {top[sa]}, {sb} in the {top[sb]}")

    # time pressure: under 10 minutes vs the player's overall accuracy
    low = {p["short"]: _bucket(p["accuracy_by_clock"], "< 10 min") for p in P}
    usable = {n: r for n, r in low.items() if r and r["moves"] >= MIN_N and r["accuracy"] is not None}
    if len(usable) < 2:
        out["pressure"] = "Too few moves with under 10 minutes left to say anything yet"
    else:
        slipped = [p["short"] for p in P if usable[p["short"]]["accuracy"] < p["accuracy"] - 1]
        if not slipped:
            out["pressure"] = "Neither player has slipped with under 10 minutes left"
        elif len(slipped) == 2:
            out["pressure"] = "Both players have been less accurate with under 10 minutes left"
        else:
            n = slipped[0]
            pa = next(p for p in P if p["short"] == n)
            out["pressure"] = f"{n} has been less accurate with under 10 minutes left ({usable[n]['accuracy']}% vs {pa['accuracy']}% overall)"

    # long thinks: over 15 min vs under 1 min
    verdict = {}
    for p in P:
        lo, hi = _bucket(p["accuracy_by_think"], "< 1 min"), _bucket(p["accuracy_by_think"], "> 15 min")
        if lo and hi and hi["moves"] >= MIN_N and lo["moves"] >= MIN_N and None not in (lo["accuracy"], hi["accuracy"]):
            verdict[p["short"]] = hi["accuracy"] > lo["accuracy"]
    if len(verdict) < 2:
        out["think"] = "Too few long thinks to judge yet"
    elif not any(verdict.values()):
        out["think"] = "So far, longer thinks haven't meant more accurate moves"
    elif all(verdict.values()):
        out["think"] = "Longer thinks have produced more accurate moves"
    else:
        yes = next(n for n, v in verdict.items() if v)
        no = next(n for n, v in verdict.items() if not v)
        out["think"] = f"Long thinks have paid off for {yes}, not for {no}"

    # hard positions
    hard = {p["short"]: p.get("accuracy_hard") or {} for p in P}
    if any((h.get("moves") or 0) < MIN_N or h.get("accuracy") is None for h in hard.values()):
        out["hard"] = "Too few hard positions to compare yet"
    elif all(h["accuracy"] >= 99.5 for h in hard.values()):
        out["hard"] = "Both were near-perfect when only a few good moves existed"
    else:
        better, worse = sorted(hard, key=lambda n: -hard[n]["accuracy"])
        out["hard"] = (f"{better} has handled hard positions better ({hard[better]['accuracy']}% vs {hard[worse]['accuracy']}%)"
                       if hard[better]["accuracy"] - hard[worse]["accuracy"] >= 1 else "Both have handled hard positions about equally well")
    return out


def prep_series(docs: list[dict], display: dict) -> dict:
    """{games: [round...], players: {short: [seconds...]}} for the prep-time chart."""
    docs = sorted(docs, key=lambda d: d["id"])
    names: dict[str, list] = {}
    rounds = []
    for d in docs:
        rounds.append(int(str(d["round"]).split(".")[0]))
        for side in ("white", "black"):
            nm = display.get(d["players"][side]["name"], {}).get("short", d["players"][side]["name"])
            names.setdefault(nm, []).append(d["summary"]["players"][side]["time_before_novelty"])
    return {"games": rounds, "players": names, "headline": prep_headline({k: [v for v in vs if v is not None] for k, vs in names.items()}),
            "text": {k: [fmt_dur(v) if v is not None else "—" for v in vs] for k, vs in names.items()}}
