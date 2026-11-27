import json
from pathlib import Path

import pytest

from storyteller import gist

DISPLAY = {"Gukesh D": {"short": "Gukesh"}, "Sindarov, Javokhir": {"short": "Sindarov"}}
GAME = Path(__file__).resolve().parents[1] / "web" / "data" / "games" / "game-03.json"


@pytest.fixture
def doc():
    if not GAME.exists():
        pytest.skip("needs built game data")
    return json.loads(GAME.read_text())


def test_facts_use_names_and_real_moves(doc):
    f = gist.gist_facts(doc, DISPLAY)
    assert f["white"] == "Sindarov" and f["result"] == "draw"
    labels = {m["label"] for m in doc["moves"]}
    assert all(t["move"] in labels for t in f["turning_points"])
    low = f["players"]["Sindarov"]["lowest_clock_before_move_40_bonus"]
    assert low.endswith(tuple(labels))                      # "8s after 39.Bb4"


def test_guard_rejects_invented_moves_but_allows_fact_moves(doc):
    f = gist.gist_facts(doc, DISPLAY)
    assert gist.ungrounded("Sindarov left theory with 14.a3 and Gukesh took on f4 with 29...gxf4.", f) == []
    assert gist.ungrounded("The engine wanted 30.Qh5 instead.", f) == ["Qh5"]


def test_template_without_claude(doc, monkeypatch, tmp_path):
    from storyteller.cache import Cache
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_PROFILE", raising=False)
    out = gist.game_gist(doc, {"enabled": True, "model": "x"}, Cache(tmp_path / "c.sqlite"), DISPLAY)
    assert out["source"] == "template" and out["sections"] and "facts" in out
    text = " ".join(s["text"] for s in out["sections"])
    assert gist.ungrounded(text, out["facts"]) == []
    assert not gist._PRONOUN.search(text)
