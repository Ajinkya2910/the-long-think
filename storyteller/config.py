from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path

    def __getitem__(self, key: str) -> dict[str, Any]:
        return self.raw[key]

    @property
    def data_dir(self) -> Path:
        return self.root / self.raw["paths"]["data_dir"]

    @property
    def web_data_dir(self) -> Path:
        return self.root / self.raw["paths"]["web_data_dir"]

    @property
    def engine_path(self) -> str:
        """STOCKFISH_PATH, else the configured path if it resolves, else common install locations."""
        configured = os.environ.get("STOCKFISH_PATH") or self.raw["engine"]["path"]
        if shutil.which(configured):
            return configured
        for candidate in ("/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish", "/usr/games/stockfish", "/usr/bin/stockfish"):
            if os.access(candidate, os.X_OK):
                return candidate
        return configured

    @property
    def lichess_token(self) -> str | None:
        return os.environ.get("LICHESS_TOKEN") or None


def load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from .env into the environment (real env vars win)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        value = value.strip("'\"")
        if key and value:
            os.environ.setdefault(key, value)


def load_config(path: str | Path | None = None) -> Config:
    load_dotenv(ROOT / ".env")
    p = Path(path) if path else Path(os.environ.get("LONGTHINK_CONFIG", ROOT / "config.toml"))
    with open(p, "rb") as f:
        raw = tomllib.load(f)
    if "ENGINE_DEPTH" in os.environ:
        raw["engine"]["depth"] = int(os.environ["ENGINE_DEPTH"])
    return Config(raw=raw, root=p.resolve().parent)
