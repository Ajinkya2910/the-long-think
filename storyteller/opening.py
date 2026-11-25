"""Opening pass: walk the game through the Lichess masters explorer until it leaves theory.

Endpoint: GET https://explorer.lichess.ovh/masters?fen=...  (no auth needed at
time of writing; LICHESS_TOKEN is sent if set in case that changes).
"""
from __future__ import annotations

import logging
import time

import requests

from .cache import Cache
from .config import Config
from .ingest import UA, ParsedGame

log = logging.getLogger(__name__)


def _query(cfg: Config, cache: Cache, fen: str) -> dict | None:
    hit = cache.get("masters", fen)
    if hit is not None:
        return hit
    headers = dict(UA)
    if cfg.lichess_token:
        headers["Authorization"] = f"Bearer {cfg.lichess_token}"
    url = f"{cfg['lichess']['explorer']}/masters"
    for attempt in range(3):
        r = requests.get(url, params={"fen": fen, "moves": 30, "topGames": 0}, headers=headers, timeout=30)
        if r.status_code == 429:
            log.warning("explorer rate-limited; sleeping 60s")
            time.sleep(60)
            continue
        if r.status_code in (401, 403):
            log.warning("explorer needs auth (HTTP %s); set LICHESS_TOKEN", r.status_code)
            return None
        r.raise_for_status()
        data = r.json()
        cache.put("masters", fen, data)
        time.sleep(cfg["lichess"]["request_pause_s"])
        return data
    return None


def opening_pass(cfg: Config, cache: Cache, game: ParsedGame) -> dict:
    min_games = int(cfg["opening"]["min_master_games"])
    book: list[dict] = []
    novelty_ply = None
    for ply, san in enumerate(game.sans):
        data = _query(cfg, cache, game.fens[ply])
        if data is None:
            return {"available": False, "novelty_ply": None, "book": book}
        match = next((m for m in data.get("moves", []) if m["san"] == san), None)
        games = (match["white"] + match["draws"] + match["black"]) if match else 0
        total = data["white"] + data["draws"] + data["black"]
        if games < min_games:
            novelty_ply = ply
            alternatives = sorted(data.get("moves", []), key=lambda m: -(m["white"] + m["draws"] + m["black"]))[:3]
            return {
                "available": True,
                "novelty_ply": ply,
                "position_games": total,
                "book_alternatives": [
                    {"san": m["san"], "games": m["white"] + m["draws"] + m["black"]} for m in alternatives
                ],
                "book": book,
            }
        book.append({"ply": ply, "san": san, "games": games})
    return {"available": True, "novelty_ply": novelty_ply, "book": book}
