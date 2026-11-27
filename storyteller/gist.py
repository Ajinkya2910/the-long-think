"""Whole-game gist: a computed facts pack, written up by Claude (or a template).

Same rules as the critical-moment narratives: the model gets only numbers computed
here, every move it mentions must appear in the facts, and players are named
instead of referred to with pronouns. Anything that fails a check falls back to
the template, which is written from the same facts.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re

import chess

from .cache import Cache
from .narrative import _claude_available, fmt_dur, short

log = logging.getLogger(__name__)
PROMPT_VERSION = "gist-v2"

_PIECE = {chess.QUEEN: "Q", chess.ROOK: "R", chess.BISHOP: "B", chess.KNIGHT: "N", chess.PAWN: "P"}
_RESULT = {"1-0": "white", "0-1": "black", "1/2-1/2": "draw"}


def _pawns(ev: dict) -> float | str:
    if ev.get("mate") is not None:
        return f"mate for {'White' if ev['mate'] > 0 else 'Black'}"
    return round(ev["cp"] / 100, 2)


def material(fen: str) -> dict:
    b = chess.Board(fen)
    out = {}
    for color, name in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        out[name] = " ".join(f"{len(b.pieces(pt, color))}{_PIECE[pt]}" for pt in _PIECE if b.pieces(pt, color)) or "king only"
    return out


def _edge(moves: list[dict], side: str) -> dict | None:
    """Largest engine edge for `side` (White POV cp, flipped for Black) after any move in `moves`."""
    sign = 1 if side == "white" else -1
    best = None
    for m in moves:
        ev = m["eval_after"]
        v = (10000 if ev["mate"] * sign > 0 else -10000) if ev.get("mate") else ev["cp"] * sign
        if best is None or v > best[0]:
            best = (v, m)
    if not best or best[0] <= 0:
        return None
    v, m = best
    return {"pawns": round(v / 100, 2) if abs(v) < 10000 else "forced mate", "after": m["label"], "win_chance_pct": round(m["eval_after"]["wp"] if side == "white" else 100 - m["eval_after"]["wp"], 1)}


def _gap(sec: int, player: str) -> str:
    if abs(sec) < 30:
        return "clocks about level"
    return f"{player} {fmt_dur(abs(sec))} {'ahead' if sec > 0 else 'behind'} on the clock"


def gist_facts(doc: dict, display: dict) -> dict:
    s, moves = doc["summary"], doc["moves"]
    name = {side: short(doc["players"][side]["name"], display) for side in ("white", "black")}
    res = _RESULT.get(doc["result"])
    p = s["players"]

    phases = []
    for ph in ("opening", "middlegame", "endgame"):
        ms = [m for m in moves if m["phase"] == ph]
        if not ms:
            continue
        phases.append({
            "phase": ph, "from_move": ms[0]["label"], "to_move": ms[-1]["label"], "plies": len(ms),
            "eval_at_end_pawns_white_pov": _pawns(ms[-1]["eval_after"]),
            "largest_edge_white": _edge(ms, "white"), "largest_edge_black": _edge(ms, "black"),
            "time_used": {name[sd]: fmt_dur(sum((m["clock"]["spent"] or 0) for m in ms if m["side"] == sd)) for sd in ("white", "black")},
            "errors": [{"move": m["label"], "by": name[m["side"]], "kind": m["classification"]} for m in ms if m["classification"]],
        })

    nov = s.get("novelty")
    opening = {"eco": doc.get("eco"), "name": doc.get("opening_name")}
    if nov:
        other = "black" if nov["side"] == "white" else "white"
        opening.update({
            "left_theory_with": nov["label"], "left_theory_by": name[nov["side"]],
            "time_used_before_leaving_theory": {name[nov["side"]]: fmt_dur(p[nov["side"]]["time_before_novelty"]), name[other]: fmt_dur(p[other]["time_before_novelty"])},
        })
    pp = s["events"].get("prep_payoff")
    if pp:
        opening["after_leaving_theory"] = {
            "moves_measured": pp["moves_measured"], "until": pp["end_label"],
            "win_chance_change_over_these_moves_for_" + name[pp["player_side"]]: round(pp["win_chance_change"], 1),
            "clock_when_leaving_theory": _gap(pp["clock_gap_before"], name[pp["player_side"]]),
            "clock_after_those_moves": _gap(pp["clock_gap_after"], name[pp["player_side"]]),
        }

    turning = []
    for c in sorted(doc["critical_moments"], key=lambda c: c["ply"]):
        m = moves[c["ply"]]
        turning.append({
            "move": m["label"], "by": name[m["side"]], "time_spent": fmt_dur(m["clock"]["spent"]),
            "engine_rank_of_move": m["played_rank"], "classification": m["classification"],
            "eval_before_pawns_white_pov": _pawns(m["eval_before"]), "eval_after_pawns_white_pov": _pawns(m["eval_after"]),
            "summary": c.get("narrative", {}).get("headline"),
        })

    last = moves[-1]
    low40 = {}   # lowest clock before the move-40 time bonus
    for sd in ("white", "black"):
        rem = [(m["clock"]["remaining"], m["label"]) for m in moves if m["side"] == sd and m["move_number"] <= 39 and m["clock"]["remaining"] is not None]
        if rem:
            r, lbl = min(rem)
            low40[name[sd]] = f"{fmt_dur(r)} after {lbl}"
    over15 = {sd: sum(1 for m in moves if m["side"] == sd and (m["clock"]["spent"] or 0) >= 900) for sd in ("white", "black")}

    return {
        "white": name["white"], "black": name["black"], "round": doc.get("round"),
        "result": "draw" if res == "draw" else (f"{name[res]} won" if res else "unfinished"),
        "time_control": (doc.get("time_control") or {}).get("description"),
        "time_control_note": "Each player gets extra time after move 40, so time pressure only matters before move 40 unless a clock runs low again later.",
        "moves": last["move_number"],
        "opening": opening,
        "phases": phases,
        "turning_points": turning,
        "missed_chances": [{"error": mc["error_label"], "by": name[mc["error_side"]], "not_punished_by": mc["reply_label"]} for mc in s["events"].get("missed_chances", [])],
        "reactions_to_surprises": [{"surprise": r["trigger_label"], "kind": r["trigger_kinds"], "answer": r["response_label"], "by": name[r["response_side"]], "time": fmt_dur(r["spent"]), "times_the_players_usual_think": round(r["ratio"], 1)} for r in s["events"].get("reactions", [])[:3]],
        "players": {name[sd]: {
            "colour": sd, "accuracy_pct": p[sd]["accuracy"], "inaccuracies": p[sd]["inaccuracies"], "mistakes": p[sd]["mistakes"], "blunders": p[sd]["blunders"],
            "time_used": fmt_dur(p[sd]["time_used"]), "longest_think": f"{fmt_dur(p[sd]['longest_think']['seconds'])} on {p[sd]['longest_think']['label']}" if p[sd].get("longest_think") else None,
            "thinks_of_15_min_or_more": over15[sd], "moves_before_40_with_under_5_min": p[sd]["time_trouble_moves"],
            "lowest_clock_before_move_40_bonus": low40.get(name[sd]), "clock_at_end": fmt_dur(p[sd]["final_clock"]),
        } for sd in ("white", "black")},
        "ending": {"last_moves": [m["label"] for m in moves[-6:]], "final_eval_pawns_white_pov": _pawns(last["eval_after"]), "material_left": {name[k]: v for k, v in material(last["fen_after"]).items()}},
    }


# ---------------------------------------------------------------- checks

_SAN = re.compile(r"(?<![\w-])(\d+\.+)?(O-O(?:-O)?|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)(?![\w])")
_PRONOUN = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.I)


def _labels(facts: dict) -> set[str]:
    blob = json.dumps(facts, ensure_ascii=False)
    return {m.group(2).rstrip("+#") for m in _SAN.finditer(blob)}


def ungrounded(text: str, facts: dict) -> list[str]:
    ok = _labels(facts)
    squares = {re.findall(r"[a-h][1-8]", s)[-1] for s in ok if re.findall(r"[a-h][1-8]", s)}
    found = {m.group(2) for m in _SAN.finditer(text)}
    return sorted(t for t in found if t.rstrip("+#") not in ok and not (re.fullmatch(r"[a-h][1-8]", t) and t in squares))


def _all_text(out: dict) -> str:
    return " ".join([out["headline"], out["summary"]] + [x["title"] + " " + x["text"] for x in out["sections"]] + [t["point"] for t in out["takeaways"]])


# ---------------------------------------------------------------- template

def template(f: dict) -> dict:
    W, B = f["white"], f["black"]
    o = f["opening"]
    secs = []
    t = f"{W} had White in {o.get('name') or 'the opening'} ({o.get('eco')})."
    if o.get("left_theory_with"):
        tu = o["time_used_before_leaving_theory"]
        t += f" Known theory ended at {o['left_theory_with']}, played by {o['left_theory_by']}; by then " + " and ".join(f"{k} had used {v}" for k, v in tu.items()) + "."
    secs.append({"title": "Opening", "text": t})
    for ph in f["phases"]:
        if ph["phase"] == "opening":
            continue
        bits = [f"From {ph['from_move']} to {ph['to_move']}."]
        for side, nm in (("largest_edge_white", W), ("largest_edge_black", B)):
            e = ph[side]
            if e and isinstance(e["pawns"], (int, float)) and e["pawns"] >= 0.3:
                bits.append(f"{nm}'s largest engine edge was {e['pawns']:+.2f} after {e['after']}.")
        if ph["errors"]:
            bits.append("Errors: " + ", ".join(f"{x['move']} ({x['by']}, {x['kind']})" for x in ph["errors"]) + ".")
        bits.append("Time used: " + ", ".join(f"{k} {v}" for k, v in ph["time_used"].items()) + ".")
        secs.append({"title": ph["phase"].capitalize(), "text": " ".join(bits)})
    pl = f["players"]
    secs.append({"title": "Result", "text": f"The game ended as a {f['result']} after {f['moves']} moves, with the engine at {f['ending']['final_eval_pawns_white_pov']} for White. "
                 + " ".join(f"{k} finished with {v['clock_at_end']} on the clock and {v['accuracy_pct']}% accuracy." for k, v in pl.items())})
    return {
        "headline": f"{W} vs {B}: {f['result']} in {f['moves']} moves",
        "summary": secs[0]["text"],
        "sections": secs,
        "takeaways": [],
        "source": "template",
    }


# ---------------------------------------------------------------- Claude

SYSTEM = """You write the summary of one world championship chess game for casual fans.

You receive a JSON object of facts computed by a chess engine, the players' clocks and the opening database. Rules:
- Use ONLY the facts given. Do not evaluate positions yourself, and never invent moves, plans, threats or variations.
- Never mention a chess move that does not appear in the facts; write moves exactly as given (e.g. 21.c3).
- Evaluations are in pawns from White's point of view; say "the engine" when citing them. Under about 0.3 pawns is
  roughly level; say so rather than inflating small numbers.
- Refer to the players by name, never with pronouns. Write sentences that read naturally without pronouns
  (e.g. "Sindarov replied with a long think" rather than "long thinks of Sindarov's own").
- Time pressure before move 40 ends at move 40, when extra time is added; do not describe later moves as played in time
  trouble unless the facts show a low clock then.
- Keep cause and effect to what the facts state; do not link two numbers as cause and effect unless the facts do.
- Use hedged language for anything about what a player intended or felt.

Write:
1. headline: at most 10 words, capturing the character of the game.
2. summary: 2 sentences, the whole game in a nutshell.
3. sections: 3 or 4 sections that follow the game in order (for example Opening, Middlegame, Endgame, or how it ended),
   each with a short title and 3 to 5 sentences. Cover who was better and when, the turning points, the errors, how the
   clock shaped the game (long thinks, time pressure before move 40), and how it finished.
4. takeaways: 3 short one-sentence observations a fan should remember, each with the fact keys it rests on (top-level
   keys such as "opening", "phases", "turning_points", "players", "ending", "reactions_to_surprises", "missed_chances")."""

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


def game_gist(doc: dict, ncfg: dict, cache: Cache, display: dict) -> dict:
    facts = gist_facts(doc, display)
    base = {**template(facts), "facts": facts}
    if not ncfg.get("enabled") or not _claude_available():
        return base
    model = ncfg["model"]
    key = hashlib.sha256(json.dumps([PROMPT_VERSION, model, SYSTEM, facts], sort_keys=True).encode()).hexdigest()
    if (hit := cache.get("gist", key)) is not None:
        return {**hit, "facts": facts}
    try:
        import anthropic

        client = anthropic.Anthropic()
        messages = [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]
        for attempt in range(2):
            resp = client.beta.messages.create(
                model=model, max_tokens=16000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                system=SYSTEM,
                output_config={"effort": ncfg.get("effort", "medium"), "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=messages,
            )
            if resp.stop_reason in ("refusal", "max_tokens"):
                log.warning("gist stopped (%s); using template", resp.stop_reason)
                return base
            out = json.loads(next(b.text for b in resp.content if b.type == "text"))
            text = _all_text(out)
            problems = []
            if (bad := ungrounded(text, facts)):
                problems.append(f"it mentions moves that are not in the facts ({', '.join(bad)}); remove them or use moves from the facts")
            if (pr := sorted({x.lower() for x in _PRONOUN.findall(text)})):
                problems.append(f"it uses pronouns for players ({', '.join(pr)}); use the players' names instead")
            if not problems:
                break
            if attempt == 0:
                log.info("gist for %s needs a rewrite: %s", doc["id"], "; ".join(problems))
                messages += [{"role": "assistant", "content": resp.content},
                             {"role": "user", "content": "Rewrite the same answer, changing nothing else, except: " + "; ".join(problems) + "."}]
            else:
                log.warning("gist for %s still failed checks (%s); using template", doc["id"], "; ".join(problems))
                return {**base, "rejected": {"problems": problems}}
        result = {**out, "takeaways": [{"point": t["point"], "based_on": [k for k in t["based_on"] if k in facts]} for t in out["takeaways"]],
                  "source": "claude", "model": resp.model}
        cache.put("gist", key, result)
        return {**result, "facts": facts}
    except Exception as e:
        log.warning("gist failed for %s: %s; using template", doc["id"], e)
        return base
