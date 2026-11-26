"""longthink CLI.

  longthink run                 # fetch broadcast, analyse every played game
  longthink run --game game-01  # just one game
  longthink run --pgn my.pgn    # analyse a local PGN instead of the broadcast
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .build import analyse_game, write_outputs
from .cache import Cache
from .config import load_config
from .engine import Engine
from .ingest import fetch_broadcast, load_games


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="longthink")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="ingest + analyse + write web/data")
    run.add_argument("--config")
    run.add_argument("--pgn", type=Path, help="local PGN file instead of the Lichess broadcast")
    run.add_argument("--game", action="append", help="game id(s) to (re)analyse, e.g. game-01")
    run.add_argument("--refresh", action="store_true", help="re-download PGNs even if cached")
    run.add_argument("--depth", type=int, help="override engine depth")
    run.add_argument("--skip-opening", action="store_true")
    run.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(args.config)
    if args.depth:
        cfg.raw["engine"]["depth"] = args.depth
    cache = Cache(cfg.data_dir / "cache" / "cache.sqlite")
    paths = [args.pgn] if args.pgn else fetch_broadcast(cfg, refresh=args.refresh)
    games = load_games(paths)
    logging.info("%d played game(s) found", len(games))

    # Keep already-built games that we are not re-analysing.
    out_games = cfg.web_data_dir / "games"
    engine = Engine(cfg, cache)
    docs = []
    try:
        for g in games:
            existing = out_games / f"{g.game_id}.json"
            if args.game and g.game_id not in args.game and existing.exists():
                doc = json.loads(existing.read_text())
                from .patterns import game_summary
                doc["summary"] = game_summary(doc, cfg.raw.get("patterns"))
                docs.append(doc)
                continue
            docs.append(analyse_game(cfg, cache, engine, g, skip_opening=args.skip_opening))
    finally:
        engine.close()
    write_outputs(cfg, docs)


if __name__ == "__main__":
    main()
