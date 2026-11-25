from __future__ import annotations

import os
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
        return os.environ.get("STOCKFISH_PATH") or self.raw["engine"]["path"]

    @property
    def lichess_token(self) -> str | None:
        return os.environ.get("LICHESS_TOKEN") or None


def load_config(path: str | Path | None = None) -> Config:
    p = Path(path) if path else Path(os.environ.get("LONGTHINK_CONFIG", ROOT / "config.toml"))
    with open(p, "rb") as f:
        raw = tomllib.load(f)
    if "ENGINE_DEPTH" in os.environ:
        raw["engine"]["depth"] = int(os.environ["ENGINE_DEPTH"])
    return Config(raw=raw, root=p.resolve().parent)
