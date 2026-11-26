"""Download broadcast PGNs from Lichess and parse them with python-chess."""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn
import requests

from .config import Config

log = logging.getLogger(__name__)
UA = {"User-Agent": "long-think-chess-storyteller/0.1"}


@dataclass
class ParsedGame:
    game_id: str
    headers: dict[str, str]
    sans: list[str]
    ucis: list[str]
    fens: list[str]               # fens[i] = position BEFORE ply i; len = plies + 1
    clocks: list[int | None]      # %clk after each ply, seconds
    broadcast_evals: list[float | None]
    pgn: str

    @property
    def plies(self) -> int:
        return len(self.sans)


def _session(cfg: Config) -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    if cfg.lichess_token:
        s.headers["Authorization"] = f"Bearer {cfg.lichess_token}"
    return s


def fetch_broadcast(cfg: Config, refresh: bool = False) -> list[Path]:
    """Fetch every round's PGN of the configured broadcast into data/raw.

    Endpoints (Lichess API docs, "Broadcasts"):
      GET /api/broadcast/{tournamentId}            -> tournament + rounds (JSON)
      GET /api/broadcast/round/{roundId}.pgn       -> PGN of one round
    """
    base = cfg["lichess"]["base"]
    bid = cfg["match"]["broadcast_id"]
    raw_dir = cfg.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    s = _session(cfg)
    r = s.get(f"{base}/api/broadcast/{bid}", timeout=30)
    r.raise_for_status()
    rounds = r.json().get("rounds", [])
    import json
    (raw_dir / "rounds.json").write_text(json.dumps(
        [{"id": rd["id"], "name": rd.get("name"), "startsAt": rd.get("startsAt"), "finished": bool(rd.get("finished"))} for rd in rounds],
        indent=1))
    paths = []
    for rd in rounds:
        path = raw_dir / f"{rd['slug'] if 'slug' in rd else rd['id']}.pgn"
        if path.exists() and not refresh and _is_complete(path):
            paths.append(path)
            continue
        pr = s.get(f"{base}/api/broadcast/round/{rd['id']}.pgn", timeout=30)
        if pr.status_code != 200:
            log.warning("round %s: HTTP %s", rd["id"], pr.status_code)
            continue
        path.write_text(pr.text)
        paths.append(path)
        log.info("fetched %s (%s)", rd.get("name"), rd["id"])
    return paths


def _is_complete(path: Path) -> bool:
    """Reuse a cached round only if every game in it has moves and a final result."""
    games = parse_pgn_text(path.read_text())
    return bool(games) and all(g.headers.get("Result", "*") != "*" for g in games)


_CLK = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]")
_EVAL = re.compile(r"\[%eval\s+(#?-?[\d.]+)\]")


def _clock(comment: str) -> int | None:
    m = _CLK.search(comment or "")
    if not m:
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(float(s))


def _beval(comment: str) -> float | None:
    m = _EVAL.search(comment or "")
    if not m or m.group(1).startswith("#"):
        return None
    return float(m.group(1))


def game_id_for(headers: dict[str, str]) -> str:
    rnd = headers.get("Round", "?").split(".")[0]
    if rnd.isdigit():
        return f"game-{int(rnd):02d}"
    url = headers.get("GameURL", "")
    return url.rstrip("/").split("/")[-1] or "game"


def parse_pgn_text(text: str) -> list[ParsedGame]:
    games = []
    stream = io.StringIO(text)
    while (g := chess.pgn.read_game(stream)) is not None:
        headers = dict(g.headers)
        board = g.board()
        sans, ucis, fens, clocks, evals = [], [], [board.fen()], [], []
        for node in g.mainline():
            sans.append(board.san(node.move))
            ucis.append(node.move.uci())
            board.push(node.move)
            fens.append(board.fen())
            clocks.append(_clock(node.comment))
            evals.append(_beval(node.comment))
        if not sans:
            continue  # round not played yet
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
        games.append(ParsedGame(game_id_for(headers), headers, sans, ucis, fens, clocks, evals, g.accept(exporter)))
    return games


def load_games(paths: list[Path]) -> list[ParsedGame]:
    seen: dict[str, ParsedGame] = {}
    for p in paths:
        for g in parse_pgn_text(p.read_text()):
            seen[g.game_id] = g
    return [seen[k] for k in sorted(seen)]


def read_pairings(paths: list[Path]) -> list[dict]:
    """Every scheduled game (played or not) from PGN headers: round, colours, ratings, result."""
    out: dict[int, dict] = {}
    for p in paths:
        stream = io.StringIO(p.read_text())
        while (headers := chess.pgn.read_headers(stream)) is not None:
            rnd = headers.get("Round", "?").split(".")[0]
            if not rnd.isdigit() or not headers.get("White") or not headers.get("Black"):
                continue
            out[int(rnd)] = {
                "round": int(rnd),
                "white": headers["White"],
                "black": headers["Black"],
                "white_elo": int(headers["WhiteElo"]) if headers.get("WhiteElo", "").isdigit() else None,
                "black_elo": int(headers["BlackElo"]) if headers.get("BlackElo", "").isdigit() else None,
                "result": headers.get("Result", "*"),
            }
    return [out[k] for k in sorted(out)]
