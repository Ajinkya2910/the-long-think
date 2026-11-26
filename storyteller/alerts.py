"""Insight alerts: what changed after each game.

For every game k (in round order) we look at games 1..k and emit alerts that
became true *with* game k:

* record  - game k set a new high/low for a metric (needs >= min_games games;
            with only two games every value is trivially a high or a low)
* streak  - a metric rose (or fell) in each of the last >= 3 games
* first   - the first time something happened in the match
            (decisive result, mistake/blunder, missed chance, time trouble)

Every alert carries the series it was computed from as evidence.
"""
from __future__ import annotations

from .narrative import fmt_dur

SIDES = ("white", "black")


def _round(doc: dict) -> int:
    try:
        return int(str(doc.get("round") or "0").split(".")[0])
    except ValueError:
        return 0


def _game_name(doc: dict) -> str:
    return f"Game {_round(doc)}"


def player_metrics(doc: dict, side: str) -> dict:
    ps = doc["summary"]["players"][side]
    ev = doc["summary"].get("events") or {}
    rx = [r for r in ev.get("reactions", []) if r["response_side"] == side and "novelty" in r["trigger_kinds"] and r["spent"] is not None]
    return {
        "accuracy": ps["accuracy"],
        "time_used": ps["time_used"],
        "longest_think": (ps["longest_think"] or {}).get("seconds"),
        "longest_think_label": (ps["longest_think"] or {}).get("label"),
        "prep_time": ps["time_before_novelty"],
        "reaction_to_novelty": rx[0]["spent"] if rx else None,
        "errors": ps["mistakes"] + ps["blunders"],
        "time_trouble_moves": ps["time_trouble_moves"],
        "missed_chances": sum(1 for m in ev.get("missed_chances", []) if m["reply_side"] == side),
    }


# metric -> (unit formatter, high text, low text); None = don't report that direction
RECORDS = {
    "longest_think": (fmt_dur, "the longest single think of the match so far{extra}", None),
    "prep_time": (fmt_dur, "the most time used before leaving theory in any game so far", "the least time used before leaving theory in any game so far"),
    "accuracy": (lambda v: f"{v:.1f}%", "the highest accuracy of the match so far", "the lowest accuracy of the match so far"),
    "time_used": (fmt_dur, "the most total thinking time in a game so far", None),
    "reaction_to_novelty": (fmt_dur, "the longest answer to an opponent novelty so far", None),
}
STREAKS = {
    "prep_time": "time used before leaving theory",
    "accuracy": "accuracy",
    "time_used": "total thinking time",
    "longest_think": "longest think",
}
ORDINAL = {2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth"}


def _streak(values: list[float]) -> tuple[int, int]:
    """Length (in games) and direction (+1/-1) of the run ending at the last value."""
    if len(values) < 2:
        return 1, 0
    direction = 0
    length = 1
    for a, b in zip(reversed(values[:-1]), reversed(values)):
        step = (b > a) - (b < a)
        if step == 0 or (direction and step != direction):
            break
        direction = step
        length += 1
    return length, direction


def alerts_after(docs: list[dict], display: dict, min_games: int = 3) -> list[dict]:
    """Alerts that became true with the last game in `docs` (already in round order)."""
    if not docs:
        return []
    latest = docs[-1]
    gname = _game_name(latest)
    short = lambda name: display.get(name, {}).get("short", name.split(",")[0])
    out: list[dict] = []

    # per-player series (by name, across colours)
    names = {latest["players"][s]["name"] for s in SIDES}
    for name in sorted(names):
        series = []
        for d in docs:
            side = next((s for s in SIDES if d["players"][s]["name"] == name), None)
            if side:
                series.append({"game_id": d["id"], "game": _game_name(d), **player_metrics(d, side)})
        if not series or series[-1]["game_id"] != latest["id"]:
            continue
        n = short(name)
        cur = series[-1]

        if len(series) >= min_games:
            for metric, (fmt, hi_txt, lo_txt) in RECORDS.items():
                vals = [s[metric] for s in series if s[metric] is not None]
                if cur[metric] is None or len(vals) < 2:
                    continue
                prev = [s[metric] for s in series[:-1] if s[metric] is not None]
                if not prev:
                    continue
                if hi_txt and cur[metric] > max(prev):
                    extra = f" ({cur['longest_think_label']})" if metric == "longest_think" else ""
                    out.append(_alert(latest, name, "record", f"{gname}: {n} set {hi_txt.format(extra=extra)}: {fmt(cur[metric])} (previous high {fmt(max(prev))}).", metric, series))
                elif lo_txt and cur[metric] < min(prev):
                    out.append(_alert(latest, name, "record", f"{gname}: {n} set {lo_txt}: {fmt(cur[metric])} (previous low {fmt(min(prev))}).", metric, series))

        for metric, words in STREAKS.items():
            vals = [s[metric] for s in series]
            if any(v is None for v in vals[-3:]):
                continue
            length, direction = _streak([v for v in vals if v is not None])
            if length >= 3 and direction:
                nth = ORDINAL.get(length - 1, f"{length - 1}th")
                verb = "rose" if direction > 0 else "fell"
                out.append(_alert(latest, name, "streak", f"{n}'s {words} {verb} for the {nth} game in a row ({' → '.join(_fmt_metric(metric, v) for v in vals[-length:])}).", metric, series))

        for metric, text in (
            ("errors", f"{gname}: {n}'s first mistake of the match (engine-classified)."),
            ("missed_chances", f"{gname}: the first time {n} let an opponent error go unpunished."),
            ("time_trouble_moves", f"{gname}: the first time {n} got into time trouble (under 5 minutes before move 40)."),
        ):
            if cur[metric] and not any(s[metric] for s in series[:-1]):
                out.append(_alert(latest, name, "first", text, metric, series))

    # game-level alerts
    if latest["result"] in ("1-0", "0-1") and all(d["result"] not in ("1-0", "0-1") for d in docs[:-1]):
        winner = latest["players"]["white" if latest["result"] == "1-0" else "black"]["name"]
        draws = len(docs) - 1
        lead = f" after {draws} draw{'s' if draws != 1 else ''}" if draws else ""
        out.append(_alert(latest, winner, "first", f"{gname}: the first decisive game of the match{lead}: {short(winner)} won.", "result", []))
    depth = [(_game_name(d), d["opening"].get("novelty_ply")) for d in docs]
    known = [p for _, p in depth if p is not None]
    if len(known) >= min_games and depth[-1][1] is not None:
        cur_ply = depth[-1][1]
        prev = known[:-1]
        lbl = latest["moves"][cur_ply]["label"]
        if cur_ply < min(prev):
            out.append(_alert(latest, None, "record", f"{gname} left theory earliest so far, at {lbl} (previous earliest: move {min(prev) // 2 + 1}).", "novelty_ply", depth))
        elif cur_ply > max(prev):
            out.append(_alert(latest, None, "record", f"{gname} stayed in theory longest so far, until {lbl} (previous deepest: move {max(prev) // 2 + 1}).", "novelty_ply", depth))
    return out


def _fmt_metric(metric: str, v) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%" if metric == "accuracy" else fmt_dur(v)


def _alert(doc: dict, player: str | None, kind: str, text: str, metric: str, evidence) -> dict:
    return {"game_id": doc["id"], "game": _game_name(doc), "player": player, "kind": kind, "metric": metric, "text": text, "evidence": evidence}


def alert_history(docs: list[dict], display: dict, min_games: int = 3) -> list[dict]:
    """[{game_id, game, alerts}] for every game, oldest first."""
    ordered = sorted(docs, key=_round)
    return [
        {"game_id": d["id"], "game": _game_name(d), "alerts": alerts_after(ordered[: i + 1], display, min_games)}
        for i, d in enumerate(ordered)
    ]
