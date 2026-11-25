"""Stockfish pass: multi-PV analysis of every position, cached in SQLite."""
from __future__ import annotations

import logging

import chess
import chess.engine

from .cache import Cache
from .config import Config

log = logging.getLogger(__name__)


class Engine:
    def __init__(self, cfg: Config, cache: Cache):
        ec = cfg["engine"]
        self.depth = int(ec["depth"])
        self.multipv = int(ec["multipv"])
        self.cache = cache
        self._engine: chess.engine.SimpleEngine | None = None
        self._path = cfg.engine_path
        self._opts = {"Threads": int(ec["threads"]), "Hash": int(ec["hash_mb"])}
        self.name = "stockfish"

    def _ensure(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            self._engine = chess.engine.SimpleEngine.popen_uci(self._path)
            self._engine.configure(self._opts)
            self.name = self._engine.id.get("name", "stockfish")
        return self._engine

    def close(self) -> None:
        if self._engine:
            self._engine.quit()

    def analyse(self, fen: str) -> dict:
        """Return {'lines': [{uci, san, cp, mate, pv_san}], 'depth': d} with White-POV scores."""
        key = f"{fen}|d{self.depth}|m{self.multipv}"
        hit = self.cache.get("engine", key)
        if hit is not None:
            return hit
        board = chess.Board(fen)
        if board.is_game_over():
            outcome = board.outcome()
            cp = 0 if outcome.winner is None else (10_000 if outcome.winner else -10_000)
            res = {"lines": [], "depth": 0, "terminal": True, "cp": cp}
            self.cache.put("engine", key, res)
            return res
        eng = self._ensure()
        n = min(self.multipv, board.legal_moves.count())
        infos = eng.analyse(board, chess.engine.Limit(depth=self.depth), multipv=n)
        lines = []
        for info in infos:
            pv = info.get("pv") or []
            if not pv:
                continue
            score = info["score"].white()
            b = board.copy()
            pv_san = []
            for mv in pv[:8]:
                pv_san.append(b.san(mv))
                b.push(mv)
            lines.append({
                "uci": pv[0].uci(),
                "san": pv_san[0],
                "cp": score.score(),
                "mate": score.mate(),
                "pv_san": pv_san,
            })
        res = {"lines": lines, "depth": int(infos[0].get("depth", self.depth)), "legal": board.legal_moves.count()}
        self.cache.put("engine", key, res)
        return res
