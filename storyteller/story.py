"""Match story so far: a facts pack across every analysed game, written up by Claude.

Uses the same checks as the game gists (moves must be in the facts, players named,
one rewrite, template fallback). Crowd numbers are passed as opinion, clearly
labelled, and only from collection windows that have closed so the text doesn't
change on every run.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .cache import Cache
from .gist import claude_write, gist_facts
from .narrative import _claude_available, fmt_dur, short

log = logging.getLogger(__name__)
PROMPT_VERSION = "story-v1"


def _crowd(doc: dict, display: dict) -> dict | None:
    out = {}
    for src, c in (doc.get("crowd") or {}).items():
        if not c.get("comments_labelled") or (src == "bluesky" and not c.get("window_closed")):
            continue
        keys, counts = c["favours"]["keys"], c["favours"]["counts"]
        picked = sum(counts[k] for k in keys)
        if picked < 10:
            continue
        out[src] = {"read": c["comments_labelled"], "picked_a_side": picked,
                    **{f"backs_{short(n, display)}_pct": round(100 * counts[k] / picked) for k, n in keys.items()}}
    return out or None


def story_facts(docs: list[dict], odds: dict | None, alerts: list[dict], patterns: dict, schedule: list[dict], display: dict, players: list[str]) -> dict:
    docs = sorted(docs, key=lambda d: d["id"])
    nm = {p: short(p, display) for p in players}
    games = []
    for d in docs:
        f = (d.get("gist") or {}).get("facts") or gist_facts(d, display)
        games.append({
            "game": int(str(d["round"]).split(".")[0]), "date": (d.get("date") or "").replace(".", "-"),
            "white": f["white"], "black": f["black"], "result": f["result"], "moves": f["moves"],
            "opening": f"{f['opening'].get('name')} ({f['opening'].get('eco')})",
            "left_theory": f"{f['opening'].get('left_theory_with')} by {f['opening'].get('left_theory_by')}" if f["opening"].get("left_theory_with") else None,
            "time_used_before_leaving_theory": f["opening"].get("time_used_before_leaving_theory"),
            "players": {k: {x: v[x] for x in ("accuracy_pct", "inaccuracies", "mistakes", "blunders", "time_used", "longest_think", "lowest_clock_before_move_40_bonus")}
                        for k, v in f["players"].items()},
            "turning_points": [f"{t['move']} ({t['by']}, {t['time_spent']}): {t['summary']}" for t in f["turning_points"]],
            "final_material": f["ending"]["material_left"],
            "crowd_opinion": _crowd(d, display),
        })

    pp = patterns.get("players", {})
    totals = {}
    for p in players:
        x = pp.get(p)
        if not x:
            continue
        totals[nm[p]] = {
            "points": x["points"], "accuracy_pct": x["accuracy"],
            "share_of_time_by_phase_pct": x["time_share_by_phase"],
            "accuracy_by_think_length": {b["bucket"]: f"{b['accuracy']}% over {b['moves']} moves" for b in x["accuracy_by_think"]},
            "accuracy_in_hard_positions": f"{x['accuracy_hard']['accuracy']}% over {x['accuracy_hard']['moves']} moves" if x.get("accuracy_hard") else None,
            "novelties_played": x["novelties_played"],
            "average_time_used_before_leaving_theory": fmt_dur(x["avg_time_before_novelty"]) if x.get("avg_time_before_novelty") is not None else None,
        }

    model = None
    if odds:
        model = {
            "what_it_is": "a rating model (FIDE ratings, White bonus, fixed draw rate), not the engine's view of the games",
            "match_win_pct_by_stage": [{"stage": s["label"], **{nm.get(n, n): v for n, v in s["win"].items()}, "tiebreak": s["tiebreak"]} for s in odds["series"]],
            "next_game": ({"game": odds["next_game"]["round"], "white": nm.get(odds["next_game"]["white"]), "black": nm.get(odds["next_game"]["black"]),
                           "white_win_pct": odds["next_game"]["white_win"], "draw_pct": odds["next_game"]["draw"], "black_win_pct": odds["next_game"]["black_win"]}
                          if odds.get("next_game") else None),
        }

    nxt = next((r for r in schedule if not r.get("finished")), None)
    score = {nm[p]: totals.get(nm[p], {}).get("points", 0) for p in players}
    return {
        "players": [nm[p] for p in players],
        "games_played": len(games), "games_scheduled": len(schedule) or None,
        "score": score,
        "next_game": ({"name": nxt["name"], "date": datetime.fromtimestamp(nxt["startsAt"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")}
                      if nxt and nxt.get("startsAt") else None),
        "games": games,
        "totals": totals,
        "rating_model": model,
        "records_and_firsts": [a["text"] for g in alerts for a in g["alerts"]],
    }


SYSTEM = """You write "the story so far" of a world championship chess match for casual fans, on the site's home page.

You receive a JSON object of facts computed by a chess engine, the players' clocks, the opening database, a rating model
and (labelled crowd_opinion) counts of public comments. Rules:
- Use ONLY the facts given. Do not judge positions or players yourself and never invent moves, plans or quotes.
- Never mention a chess move that does not appear in the facts; write moves exactly as given (e.g. 21.c3).
- Refer to the players by name, never with pronouns, and write sentences that read naturally without them.
- Engine edges under about 0.3 pawns are roughly level; do not inflate them.
- The rating model is not a judgement of how well anyone played; say it comes from ratings. Crowd numbers are opinion
  from commenters, not evidence; if you mention them, say so and keep it to one sentence.
- Use hedged language for anything about intentions or feelings. Do not predict results.

Write:
1. headline: at most 10 words.
2. summary: 2 or 3 sentences: the score and the character of the match so far.
3. sections: 3 or 4 sections, each with a short title and 3 to 5 sentences. Find threads ACROSS games rather than
   retelling each game: how preparation and the openings went, how each player used the clock (and when it got
   tight), accuracy and errors, what the rating model says, and what comes next.
4. takeaways: 3 short one-sentence patterns a fan should remember, each with the top-level fact keys it rests on
   ("games", "totals", "rating_model", "records_and_firsts", "score", "next_game")."""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "sections": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "text": {"type": "string"}},
                                                "required": ["title", "text"], "additionalProperties": False}},
        "takeaways": {"type": "array", "items": {"type": "object", "properties": {"point": {"type": "string"}, "based_on": {"type": "array", "items": {"type": "string"}}},
                                                 "required": ["point", "based_on"], "additionalProperties": False}},
    },
    "required": ["headline", "summary", "sections", "takeaways"],
    "additionalProperties": False,
}


def template(f: dict) -> dict:
    a, b = f["players"]
    sc = f["score"]
    res = "; ".join(f"Game {g['game']}: {g['white']}–{g['black']}, {g['result']} in {g['moves']} moves ({g['opening']})" for g in f["games"])
    secs = [{"title": "Results", "text": res + "."}]
    t = f["totals"]
    if a in t and b in t:
        secs.append({"title": "Accuracy", "text": f"Overall accuracy: {a} {t[a]['accuracy_pct']}%, {b} {t[b]['accuracy_pct']}%."})
    if f.get("rating_model"):
        last = f["rating_model"]["match_win_pct_by_stage"][-1]
        secs.append({"title": "Rating model", "text": f"{last['stage']}: {a} {last[a]}%, {b} {last[b]}% to win the match; tiebreak {last['tiebreak']}%."})
    return {"headline": f"{a} {sc[a]:g}–{sc[b]:g} {b} after {f['games_played']} games", "summary": res + ".", "sections": secs, "takeaways": [], "source": "template"}


def match_story(docs: list[dict], odds, alerts, patterns, schedule, display: dict, players: list[str], ncfg: dict, cache: Cache | None) -> dict | None:
    if not docs:
        return None
    facts = story_facts(docs, odds, alerts, patterns, schedule, display, players)
    base = {**template(facts), "facts": facts}
    if cache is None or not ncfg.get("enabled") or not _claude_available():
        return base
    try:
        out, rejected = claude_write(SYSTEM, SCHEMA, facts, ncfg, cache, "story", PROMPT_VERSION, "match story")
    except Exception as e:
        log.warning("match story failed: %s; using template", e)
        return base
    return {**out, "facts": facts} if out else {**base, "rejected": rejected}
