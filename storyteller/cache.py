"""Tiny SQLite key/value cache so reruns never repeat engine or HTTP work."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS kv (ns TEXT, k TEXT, v TEXT, PRIMARY KEY (ns, k))")

    def get(self, ns: str, key: str) -> Any | None:
        row = self.db.execute("SELECT v FROM kv WHERE ns=? AND k=?", (ns, key)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, ns: str, key: str, value: Any) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?)", (ns, key, json.dumps(value)))
        self.db.commit()
