"""Orchestrates the passes and writes one JSON per game + match.json."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .analysis import build_moves, flag_long_thinks, rank_critical
from .cache import Cache
from .config import Config
from .engine import Engine
from .alerts import alert_history
from .events import game_events
from .ingest import read_pairings
from .match_odds import win_probability
from .opening_tree import opening_tree
from .ingest import ParsedGame
from .narrative import moment_facts, narrate
from .opening import opening_pass
from .patterns import game_summary, match_patterns
from .timecontrol import compute_spent, from_config, parse_pgn_header

log = logging.getLogger(__name__)
SCHEMA_VERSION = 1


def time_control_for(cfg: Config, game: ParsedGame):
    tc_cfg = cfg["time_control"]
    if tc_cfg.get("prefer_pgn_header"):
        parsed = parse_pgn_header(game.headers.get("TimeControl", ""))
        if parsed:
            return parsed
    return from_config(tc_cfg)


def analyse_game(cfg: Config, cache: Cache, engine: Engine, game: ParsedGame, skip_opening: bool = False) -> dict:
    display = cfg["match"].get("display", {})
    tc = time_control_for(cfg, game)
    log.info("[%s] engine pass: %d positions at depth %d", game.game_id, len(game.fens), engine.depth)
    analyses = []
    for i, fen in enumerate(game.fens):
        analyses.append(engine.analyse(fen))
        if i % 10 == 0:
            log.info("[%s]   %d/%d", game.game_id, i, len(game.fens))
    clocks = compute_spent(game.clocks, tc)
    opening = {"available": False, "novelty_ply": None, "book": []}
    if not skip_opening:
        log.info("[%s] opening pass", game.game_id)
        try:
            opening = opening_pass(cfg, cache, game)
        except Exception as e:
            log.warning("opening pass failed: %s", e)
    moves = build_moves(game, analyses, clocks, opening, cfg)
    flag_long_thinks(moves, int(cfg["clock"]["long_think_seconds"]), int(cfg["clock"]["long_think_top_n"]))
    h = game.headers
    doc = {
        "schema_version": SCHEMA_VERSION,
        "id": game.game_id,
        "round": h.get("Round"),
        "date": h.get("Date"),
        "event": h.get("Event"),
        "site": h.get("Site"),
        "result": h.get("Result", "*"),
        "eco": h.get("ECO"),
        "opening_name": h.get("Opening"),
        "game_url": h.get("GameURL"),
        "players": {
            "white": {"name": h.get("White"), "elo": h.get("WhiteElo"), "short": display.get(h.get("White"), {}).get("short"), "slot": display.get(h.get("White"), {}).get("slot", 1)},
            "black": {"name": h.get("Black"), "elo": h.get("BlackElo"), "short": display.get(h.get("Black"), {}).get("short"), "slot": display.get(h.get("Black"), {}).get("slot", 2)},
        },
        "time_control": tc.to_dict(),
        "engine": {"name": engine.name, "depth": engine.depth, "multipv": engine.multipv},
        "initial_eval": analyses[0]["lines"][0] and {"cp": analyses[0]["lines"][0]["cp"], "mate": analyses[0]["lines"][0]["mate"]},
        "opening": opening,
        "moves": moves,
        "critical_moments": [],
        "pgn": game.pgn,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    events = game_events(doc, cfg.raw.get("patterns"))
    for mc in events["missed_chances"]:
        moves[mc["reply_ply"]]["tags"].append("missed_chance")
    crit = rank_critical(moves, cfg["critical"])
    for c in crit:
        facts = moment_facts(doc, c["ply"], display)
        c["facts"] = facts
        c["narrative"] = narrate(facts, cfg["narrative"], cache)
        moves[c["ply"]]["tags"].append("critical")
    doc["critical_moments"] = crit
    doc["summary"] = game_summary(doc, events=events)
    return doc


def write_outputs(cfg: Config, docs: list[dict], cache: Cache | None = None) -> None:
    out = cfg.web_data_dir
    (out / "games").mkdir(parents=True, exist_ok=True)
    display = cfg["match"].get("display", {})
    patterns = match_patterns(docs, display)
    index = []
    for doc in docs:
        rows = doc["summary"].pop("_rows", None)
        (out / "games" / f"{doc['id']}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        doc["summary"]["_rows"] = rows
        index.append({
            "id": doc["id"],
            "round": doc["round"],
            "date": doc["date"],
            "result": doc["result"],
            "white": doc["players"]["white"],
            "black": doc["players"]["black"],
            "eco": doc["eco"],
            "opening_name": doc["opening_name"],
            "plies": len(doc["moves"]),
            "novelty": doc["summary"]["novelty"],
            "longest_think": doc["summary"]["longest_think"],
            "critical_count": doc["summary"]["critical_count"],
            "accuracy": {s: doc["summary"]["players"][s]["accuracy"] for s in ("white", "black")},
            "crowd": ({src: {"favours": c["favours"], "comments": c["comments_labelled"], "game_feel": c.get("game_feel")}
                       for src, c in (doc.get("crowd") or {}).items() if c.get("comments_labelled")} or None),
            "sparkline": [round(doc["moves"][0]["eval_before"]["wp"], 1)] + [round(m["eval_after"]["wp"], 1) for m in doc["moves"]],
        })
    pairings = read_pairings(sorted((cfg.data_dir / "raw").glob("*.pgn")))
    odds = win_probability(pairings, cfg["match_odds"], cfg["match"]["players"], display) if "match_odds" in cfg.raw else None
    rounds_path = cfg.data_dir / "raw" / "rounds.json"
    schedule = json.loads(rounds_path.read_text()) if rounds_path.exists() else []
    alerts_min = int(cfg.raw.get("patterns", {}).get("alerts_min_games", 3))
    alerts = alert_history(docs, display, alerts_min)
    from .story import match_story
    story = match_story(docs, odds, alerts, patterns, schedule, display, cfg["match"]["players"], cfg["narrative"], cache)
    if story:
        log.info("match story: %s (%s)", story["headline"], story["source"])
    match = {
        "story": story,
        "schedule": schedule,
        "schema_version": SCHEMA_VERSION,
        "name": cfg["match"]["name"],
        "short_name": cfg["match"]["short_name"],
        "players": cfg["match"]["players"],
        "display": display,
        "games": index,
        "patterns": patterns,
        "opening_tree": opening_tree(docs),
        "win_probability": odds,
        "alerts": alerts,
        "alerts_min_games": alerts_min,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "match.json").write_text(json.dumps(match, ensure_ascii=False, indent=1))
    log.info("wrote %d game(s) + match.json to %s", len(docs), out)
