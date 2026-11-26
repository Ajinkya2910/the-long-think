"""Narration of critical moments.

The LLM only ever sees `facts` (computed numbers) and must not add chess
judgements of its own. Its output is checked: any move it mentions must appear
in the facts, otherwise we fall back to the deterministic template.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re

from .cache import Cache
from .decision import move_character, position_context

log = logging.getLogger(__name__)
PROMPT_VERSION = "v3"


def fmt_dur(sec: int | None) -> str:
    if sec is None:
        return "unknown"
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def fmt_eval(ev: dict) -> str:
    if ev.get("mate") is not None:
        return f"mate in {abs(ev['mate'])} for {'White' if ev['mate'] > 0 else 'Black'}" if ev["mate"] else "checkmate"
    return f"{ev['cp'] / 100:+.2f}"


def short(name: str, display: dict) -> str:
    return display.get(name, {}).get("short", name.split(",")[0])


def moment_facts(doc: dict, ply: int, display: dict) -> dict:
    multipv = doc.get("engine", {}).get("multipv", 5)
    moves = doc["moves"]
    m = moves[ply]
    side = m["side"]
    player = short(m["player"], display)
    opp_name = doc["players"]["black" if side == "white" else "white"]["name"]
    # opponent clock = their remaining after their last move
    opp_clock = next((x["clock"]["remaining"] for x in reversed(moves[:ply]) if x["side"] != side), None)
    mine = sorted([x for x in moves if x["side"] == side and x["clock"]["spent"]], key=lambda x: -x["clock"]["spent"])
    think_rank = next((i + 1 for i, x in enumerate(mine) if x["ply"] == ply), None)
    nov = doc["opening"].get("novelty_ply")
    lines = m["top_lines"]
    mover_sign = 1 if side == "white" else -1

    def mover_eval(ev):
        if ev.get("mate") is not None:
            return f"forced mate {'for' if (ev['mate'] or 0) * mover_sign > 0 else 'against'} {player}"
        return round(mover_sign * ev["cp"] / 100, 2)

    def character(line):
        try:
            return move_character(m["fen_before"], line["pv_san"])
        except Exception:  # malformed line: leave the description out rather than guess
            return None

    prev = moves[ply - 1] if ply else None
    my_prev = [x for x in moves[:ply] if x["side"] == side]
    my_clock_before = my_prev[-1]["clock"]["remaining"] if my_prev else doc["time_control"]["periods"][0]["seconds"]
    earlier_long = [x for x in my_prev if (x["clock"]["spent"] or 0) >= 600]
    played_char = None
    try:
        played_char = move_character(m["fen_before"], [m["san"]])
    except Exception:
        pass

    return {
        "move": m["label"],
        "played_san": m["san"],
        "player": player,
        "opponent": short(opp_name, display),
        "color": side,
        "phase": m["phase"],
        "time_spent": fmt_dur(m["clock"]["spent"]),
        "time_spent_seconds": m["clock"]["spent"],
        "think_rank_for_player": think_rank,
        "player_clock_after": fmt_dur(m["clock"]["remaining"]),
        "opponent_clock": fmt_dur(opp_clock),
        "eval_before_from_player_view_pawns": mover_eval(m["eval_before"]),
        "eval_after_from_player_view_pawns": mover_eval(m["eval_after"]),
        "player_win_chance_before_pct": round(m["eval_before"]["wp"] if side == "white" else 100 - m["eval_before"]["wp"], 1),
        "player_win_chance_after_pct": round(m["eval_after"]["wp"] if side == "white" else 100 - m["eval_after"]["wp"], 1),
        "win_chance_lost_pct": m["wp_loss"],
        "classification": m["classification"] or "good or best move",
        "engine_rank_of_played_move": m["played_rank"],
        "engine_best_move": lines[0]["san"] if lines else None,
        "engine_best_line": lines[0]["pv_san"][:5] if lines else [],
        "engine_best_move_character": character(lines[0]) if lines else None,
        "engine_alternatives": [{"move": l["san"], "eval_from_player_view_pawns": mover_eval(l), "character": character(l)} for l in lines[1:3]],
        "played_move_character": played_char,
        "opponent_previous_move": {
            "move": prev["label"], "san": prev["san"], "time_spent": fmt_dur(prev["clock"]["spent"]),
            "character": _safe_char(prev["fen_before"], prev["san"]),
        } if prev else None,
        "player_clock_before": fmt_dur(my_clock_before),
        "player_clock_lead_before_seconds": (my_clock_before - opp_clock) if opp_clock is not None and my_clock_before is not None else None,
        "player_earlier_thinks_over_10_min_this_game": [{"move": x["label"], "time_spent": fmt_dur(x["clock"]["spent"])} for x in earlier_long],
        "position": position_context(m["fen_before"]),
        "who_left_theory": short(moves[nov]["player"], display) if nov is not None and nov < len(moves) else None,
        "left_theory_with": moves[nov]["label"] if nov is not None and nov < len(moves) else None,
        "good_moves_available": m["difficulty"]["good_moves"],
        "good_moves_is_lower_bound": m["difficulty"]["good_moves"] >= multipv,
        "only_move_position": m["difficulty"]["only_move"],
        "difficulty_0_to_1": m["difficulty"]["score"],
        "in_opening_book": m["in_book"],
        "is_novelty": "novelty" in m["tags"],
        "moves_since_leaving_book": (ply - nov) // 2 if nov is not None and ply >= nov else None,
        "clock_adjustment_seconds": m["clock"]["adjustment"] or None,
    }


def _safe_char(fen: str, san: str) -> dict | None:
    try:
        return move_character(fen, [san])
    except Exception:
        return None


def allowed_sans(facts: dict) -> set[str]:
    out = {facts["played_san"]}
    if facts["engine_best_move"]:
        out.add(facts["engine_best_move"])
    out.update(facts["engine_best_line"])
    out.update(a["move"] for a in facts["engine_alternatives"])
    if facts.get("opponent_previous_move"):
        out.add(facts["opponent_previous_move"]["san"])
    for key in ("player_earlier_thinks_over_10_min_this_game",):
        for x in facts.get(key) or []:
            out.add(re.sub(r"^\d+\.+", "", x["move"]))
    if facts.get("left_theory_with"):
        out.add(re.sub(r"^\d+\.+", "", facts["left_theory_with"]))
    return {s.rstrip("+#") for s in out}


_SAN = re.compile(r"(?<![\w-])(O-O(?:-O)?|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)(?![\w])")


def ungrounded_moves(text: str, facts: dict) -> list[str]:
    """Moves mentioned in `text` that are not in the facts.

    A bare square ("the king went back to g8") is fine when a move in the facts
    lands on that square; otherwise it is treated as an invented pawn move.
    """
    ok = allowed_sans(facts)
    squares = {sq for san in ok for sq in re.findall(r"[a-h][1-8]", san)[-1:]}
    found = {re.sub(r"^\d+\.+", "", t) for t in _SAN.findall(text)}
    return sorted(t for t in found if t not in ok and not (re.fullmatch(r"[a-h][1-8]", t) and t in squares))


def pawns(v) -> str:
    return f"{v:+.2f}" if isinstance(v, (int, float)) else str(v)


_PRONOUN = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.I)


def pronouns_used(out: dict) -> list[str]:
    text = " ".join([out.get("headline", ""), out.get("text", out.get("explanation", ""))] + [r["reason"] for r in out.get("likely_reasons", [])])
    return sorted({p.lower() for p in _PRONOUN.findall(text)})


def template(facts: dict) -> dict:
    p, mv = facts["player"], facts["move"]
    bits = []
    if facts["time_spent_seconds"] and facts["time_spent_seconds"] >= 300:
        rank = facts["think_rank_for_player"]
        rank_txt = f" — {p}'s longest think of the game" if rank == 1 else ""
        bits.append(f"{p} spent {facts['time_spent']} on {mv}{rank_txt}, leaving {facts['player_clock_after']} on the clock against {facts['opponent_clock']} for {facts['opponent']}.")
    else:
        bits.append(f"{p} played {mv} after {facts['time_spent']}.")
    if facts["is_novelty"]:
        bits.append("This was the first move outside the masters database: preparation was over.")
    good = facts["good_moves_available"]
    if facts["only_move_position"]:
        bits.append("The engine saw only one move that held the balance here.")
    elif good is not None and good >= 3:
        many = f"at least {good}" if good >= 5 else str(good)
        bits.append(f"The engine considered {many} moves roughly equal, so there was no single right answer.")
    cls = facts["classification"]
    best = facts["engine_best_move"]
    if facts["engine_rank_of_played_move"] == 1:
        bits.append(f"It matched the engine's top choice; the evaluation stayed at {pawns(facts['eval_after_from_player_view_pawns'])} from {p}'s side.")
    elif cls != "good or best move":
        bits.append(f"The engine rates it an {cls}" if cls[0] in "aeiou" else f"The engine rates it a {cls}")
        bits[-1] += f": {p}'s winning chances dropped by {facts['win_chance_lost_pct']:.0f} points. The engine preferred {best}."
    elif best:
        bits.append(f"The engine slightly preferred {best}, but the evaluation barely moved ({pawns(facts['eval_before_from_player_view_pawns'])} → {pawns(facts['eval_after_from_player_view_pawns'])} from {p}'s side).")
    if facts["clock_adjustment_seconds"]:
        bits.append(f"The broadcast clock also shows {fmt_dur(facts['clock_adjustment_seconds'])} added to {p}'s clock here, outside the normal increments.")
    if facts["is_novelty"]:
        kind = "out of the book"
    elif (facts["time_spent_seconds"] or 0) >= 900:
        kind = "a long think"
    elif cls != "good or best move":
        kind = cls
    elif facts["only_move_position"]:
        kind = "the only move"
    else:
        kind = "a key decision"
    headline = f"{mv}: {kind}"
    return {"headline": headline, "text": " ".join(bits), "likely_reasons": template_reasons(facts), "source": "template", "model": None}


def template_reasons(f: dict) -> list[dict]:
    """Rule-based reasons, used when Claude is unavailable."""
    out = []
    slow = (f.get("time_spent_seconds") or 0) >= 300
    if not slow:
        return out
    n = f.get("good_moves_available") or 0
    if n >= 3:
        many = f"at least {n}" if f.get("good_moves_is_lower_bound") else str(n)
        out.append({"reason": f"Many reasonable options: the engine saw {many} moves of similar value, so nothing forced the choice.", "based_on": ["good_moves_available"]})
    if f.get("only_move_position"):
        out.append({"reason": "Only one move held the position, and finding it takes calculation.", "based_on": ["only_move_position"]})
    since = f.get("moves_since_leaving_book")
    if since is not None and since <= 6:
        out.append({"reason": f"The game had left known theory only {since} move{'s' if since != 1 else ''} earlier, so preparation could no longer help.", "based_on": ["moves_since_leaving_book"]})
    kinds = [c["kind"] for c in [f.get("engine_best_move_character")] + [a.get("character") for a in f.get("engine_alternatives", [])] if c]
    if any("pawn tension" in k for k in kinds):
        out.append({"reason": "Some of the main options changed the pawn structure, a decision that is hard to undo.", "based_on": ["engine_best_move_character", "engine_alternatives"]})
    return out[:3]


SYSTEM = """You explain critical moments of a world championship chess game to casual fans.

You receive a JSON object of facts computed by a chess engine, the players' clocks, the opening database and a
move classifier. Rules:
- Use ONLY the facts given. Do not evaluate the position yourself, and never invent variations, plans or threats.
- Never mention a chess move that does not appear in the facts.
- Evaluations are in pawns from the player's point of view; say "the engine" when citing them.
- If good_moves_is_lower_bound is true, the engine only compared its top moves, so say "at least N good moves".
- Refer to the players by name rather than with pronouns.

Write:
1. headline: at most 8 words.
2. explanation: 4 to 6 short sentences in plain English. Say what happened, then what probably made the decision take
   the time it did (or why it was quick). Connect the facts: the kind of choices on the table (move characters, whether
   lines trade pieces or commit the pawn structure), what the opponent had just played, how far the game was from
   known theory, the clock situation before and after, and earlier long thinks. Use hedged language for anything about
   the player's mind ("probably", "may have", "one likely reason"); never state thoughts as fact.
3. likely_reasons: 2 or 3 short reasons the decision took time (or was fast), each one sentence, each with the fact
   keys it rests on in based_on. Only include reasons the facts actually support.
4. facts_used: every fact key you relied on."""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "explanation": {"type": "string"},
        "likely_reasons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"reason": {"type": "string"}, "based_on": {"type": "array", "items": {"type": "string"}}},
                "required": ["reason", "based_on"],
                "additionalProperties": False,
            },
        },
        "facts_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "explanation", "likely_reasons", "facts_used"],
    "additionalProperties": False,
}


def _claude_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE"))


def narrate(facts: dict, ncfg: dict, cache: Cache) -> dict:
    base = template(facts)
    if not ncfg.get("enabled") or not _claude_available():
        return base
    model = ncfg["model"]
    key = hashlib.sha256(json.dumps([PROMPT_VERSION, model, facts], sort_keys=True).encode()).hexdigest()
    hit = cache.get("narrative", key)
    if hit and not pronouns_used(hit):
        return hit
    try:
        import anthropic

        client = anthropic.Anthropic()
        messages = [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}]
        model_used = model
        for attempt in range(2):
            resp = client.beta.messages.create(
                model=model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM,
                output_config={"effort": ncfg.get("effort", "medium"), "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=messages,
            )
            if resp.stop_reason == "refusal":
                log.warning("narrative refused; using template")
                return base
            text = next(b.text for b in resp.content if b.type == "text")
            out = json.loads(text)
            model_used = resp.model
            found = pronouns_used(out)
            if not found:
                break
            if attempt == 0:
                log.info("narrative used pronouns %s; asking for a rewrite", found)
                messages += [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content": f"Rewrite the same answer, changing nothing else, but replace every pronoun for a player ({', '.join(found)}) with the player's name."},
                ]
            else:
                log.warning("narrative still used pronouns %s; using template", found)
                return {**base, "rejected": {"reason": "pronouns", "words": found}}
        reasons_text = " ".join(r["reason"] for r in out.get("likely_reasons", []))
        bad = ungrounded_moves(out["headline"] + " " + out["explanation"] + " " + reasons_text, facts)
        unknown = [k for k in out["facts_used"] if k not in facts]
        if bad:
            log.warning("narrative mentioned moves not in facts %s; using template", bad)
            return {**base, "rejected": {"reason": "ungrounded_moves", "moves": bad, "text": out["headline"] + " | " + out["explanation"] + " | " + reasons_text}}
        result = {
            "headline": out["headline"],
            "text": out["explanation"],
            "likely_reasons": [
                {"reason": r["reason"], "based_on": [k for k in r["based_on"] if k in facts]}
                for r in out.get("likely_reasons", [])
            ],
            "facts_used": [k for k in out["facts_used"] if k in facts],
            "unknown_fact_keys": unknown,
            "source": "claude",
            "model": model_used,
        }
        cache.put("narrative", key, result)
        return result
    except Exception as e:  # network, auth, schema — never break the pipeline
        log.warning("narrative failed (%s); using template", e)
        return base
