"""Validates real pipeline output (if present) against schema/game.schema.json."""
import json
from pathlib import Path

import chess
import jsonschema
import pytest

from storyteller.analysis import is_obvious

ROOT = Path(__file__).resolve().parent.parent
GAMES = sorted((ROOT / "web" / "data" / "games").glob("*.json"))


@pytest.mark.skipif(not GAMES, reason="run the pipeline first")
@pytest.mark.parametrize("path", GAMES, ids=lambda p: p.stem)
def test_game_json_matches_schema(path):
    schema = json.loads((ROOT / "schema" / "game.schema.json").read_text())
    doc = json.loads(path.read_text())
    jsonschema.validate(doc, schema)
    # every critical moment points at a real move and was narrated
    for c in doc["critical_moments"]:
        assert 0 <= c["ply"] < len(doc["moves"])
        assert c["narrative"]["text"]


def test_recapture_is_obvious():
    b = chess.Board()
    for san in ["e4", "d5", "exd5"]:
        b.push_san(san)
    assert is_obvious(b.fen(), b.parse_san("Qxd5").uci(), "e4d5")
    assert not is_obvious(b.fen(), b.parse_san("Nf6").uci(), "e4d5")
