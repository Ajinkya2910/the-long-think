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

log = logging.getLogger(__name__)
PROMPT_VERSION = "v1"


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
        "engine_alternatives": [{"move": l["san"], "eval_from_player_view_pawns": mover_eval(l)} for l in lines[1:3]],
        "good_moves_available": m["difficulty"]["good_moves"],
        "only_move_position": m["difficulty"]["only_move"],
        "difficulty_0_to_1": m["difficulty"]["score"],
        "in_opening_book": m["in_book"],
        "is_novelty": "novelty" in m["tags"],
        "moves_since_leaving_book": (ply - nov) // 2 if nov is not None and ply >= nov else None,
        "clock_adjustment_seconds": m["clock"]["adjustment"] or None,
    }


def allowed_sans(facts: dict) -> set[str]:
    out = {facts["played_san"]}
    if facts["engine_best_move"]:
        out.add(facts["engine_best_move"])
    out.update(facts["engine_best_line"])
    out.update(a["move"] for a in facts["engine_alternatives"])
    return {s.rstrip("+#") for s in out}


_SAN = re.compile(r"(?<![\w-])(O-O(?:-O)?|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)(?![\w])")


def ungrounded_moves(text: str, facts: dict) -> list[str]:
    ok = allowed_sans(facts)
    found = {re.sub(r"^\d+\.+", "", t) for t in _SAN.findall(text)}
    return sorted(t for t in found if t not in ok)


def pawns(v) -> str:
    return f"{v:+.2f}" if isinstance(v, (int, float)) else str(v)


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
    return {"headline": headline, "text": " ".join(bits), "source": "template", "model": None}


SYSTEM = """You narrate critical moments of a world championship chess game for casual fans.

You receive a JSON object of facts computed by a chess engine, the players' clocks and an opening database. Rules:
- Use ONLY the facts given. Do not evaluate the position yourself.
- Never mention a chess move that is not in the facts (played_san, engine_best_move, engine_best_line, engine_alternatives).
- Never invent variations, evaluations, plans, or psychological claims stated as fact. You may say what a player was *likely* weighing, but only in terms of the given facts (time spent, clock situation, number of good options, opening book status, evaluation change).
- Evaluations are in pawns from the player's point of view; say "the engine" when citing them.
- 2 to 4 short sentences, plain English, no jargon without a gloss. No markdown.
- Return headline (max 8 words), explanation, and facts_used: the fact keys you relied on."""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "explanation": {"type": "string"},
        "facts_used": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "explanation", "facts_used"],
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
    if hit:
        return hit
    try:
        import anthropic

        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            output_config={"effort": ncfg.get("effort", "medium"), "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
        )
        if resp.stop_reason == "refusal":
            log.warning("narrative refused; using template")
            return base
        text = next(b.text for b in resp.content if b.type == "text")
        out = json.loads(text)
        bad = ungrounded_moves(out["headline"] + " " + out["explanation"], facts)
        unknown = [k for k in out["facts_used"] if k not in facts]
        if bad:
            log.warning("narrative mentioned moves not in facts %s; using template", bad)
            return {**base, "rejected": {"reason": "ungrounded_moves", "moves": bad}}
        result = {
            "headline": out["headline"],
            "text": out["explanation"],
            "facts_used": [k for k in out["facts_used"] if k in facts],
            "unknown_fact_keys": unknown,
            "source": "claude",
            "model": resp.model,
        }
        cache.put("narrative", key, result)
        return result
    except Exception as e:  # network, auth, schema — never break the pipeline
        log.warning("narrative failed (%s); using template", e)
        return base
