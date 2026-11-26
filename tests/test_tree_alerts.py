from storyteller.alerts import _streak, alert_history, alerts_after
from storyteller.opening_tree import opening_tree

DISPLAY = {"A": {"short": "A"}, "B": {"short": "B"}}


def game(n, sans, novelty, *, white="A", black="B", result="1/2-1/2", acc=(95.0, 95.0), prep=(300, 300),
         longest=(600, 600), used=(5000, 5000), errors=(0, 0), trouble=(0, 0), missed=()):
    moves = []
    for ply, san in enumerate(sans):
        side = "white" if ply % 2 == 0 else "black"
        moves.append({"ply": ply, "san": san, "label": f"{ply // 2 + 1}{'.' if side == 'white' else '...'}{san}",
                      "side": side, "player": white if side == "white" else black})

    def ps(i):
        return {"accuracy": acc[i], "time_used": used[i], "longest_think": {"seconds": longest[i], "label": "x"},
                "time_before_novelty": prep[i], "mistakes": errors[i], "blunders": 0, "time_trouble_moves": trouble[i]}
    return {
        "id": f"game-{n:02d}", "round": f"{n}.1", "result": result,
        "players": {"white": {"name": white}, "black": {"name": black}},
        "opening": {"novelty_ply": novelty, "book": [{"ply": p, "san": s, "games": 100 - p} for p, s in enumerate(sans[:novelty or 0])]},
        "moves": moves,
        "summary": {"players": {"white": ps(0), "black": ps(1)},
                    "events": {"reactions": [], "missed_chances": [{"reply_side": s} for s in missed]}},
    }


E4 = ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O", "Nxe4"]
D4 = ["d4", "d5", "Nf3", "Nf6", "Bf4", "c5"]


# ---------------- opening tree ----------------

def test_tree_branches_and_collapses_linear_runs():
    g1 = game(1, E4, 7)
    g2 = game(2, E4[:5] + ["a6", "Ba4"], 6)          # same until 3.Bb5, then 3...a6 novelty-ish line
    g3 = game(3, D4, 5)
    t = opening_tree([g3, g1, g2])                    # input order must not matter
    assert t["games"] == ["game-01", "game-02", "game-03"]
    roots = t["segments"]
    assert [s["moves"][0]["san"] for s in roots] == ["e4", "d4"]
    e4 = roots[0]
    assert [m["san"] for m in e4["moves"]] == ["e4", "e5", "Nf3", "Nc6", "Bb5"]   # shared run collapsed
    assert e4["games"] == ["game-01", "game-02"]
    branches = {c["moves"][0]["san"]: c for c in e4["children"]}
    assert set(branches) == {"Nf6", "a6"}
    nf6 = branches["Nf6"]
    assert nf6["moves"][-1]["san"] == "Nxe4" and nf6["novelties"][0]["game_id"] == "game-01"
    assert nf6["novelties"][0]["side"] == "black"
    assert branches["a6"]["novelties"][0]["ply"] == 6 and branches["a6"]["moves"][-1]["san"] == "Ba4"


def test_tree_keeps_master_game_counts():
    t = opening_tree([game(1, D4, 5)])
    assert t["segments"][0]["moves"][0]["master_games"] == 100


def test_tree_without_book_uses_fallback():
    g = game(1, D4, None)
    t = opening_tree([g], fallback_plies=4)
    seg = t["segments"][0]
    assert len(seg["moves"]) == 4 and seg["ends"][0]["reason"] == "no book data"


# ---------------- alerts ----------------

def test_streak_helper():
    assert _streak([1, 2, 3]) == (3, 1)
    assert _streak([5, 2, 3, 4]) == (3, 1)
    assert _streak([3, 2, 1, 0]) == (4, -1)
    assert _streak([1, 1, 2]) == (2, 1)
    assert _streak([1]) == (1, 0)


def test_first_game_has_no_records_or_streaks():
    assert all(a["kind"] == "first" for a in alerts_after([game(1, D4, 5, errors=(1, 0))], DISPLAY))


def test_record_longest_think_and_least_prep():
    g1 = game(1, E4, 7, longest=(600, 900), prep=(300, 400))
    g2 = game(2, D4, 5, white="B", black="A", longest=(1200, 500), prep=(100, 500))  # B (white) thinks 1200
    assert not [a for a in alerts_after([g1, g2], DISPLAY) if a["kind"] == "record"]   # 2 games: no records
    texts = [a["text"] for a in alerts_after([g1, g2], DISPLAY, min_games=2)]
    assert any("B set the longest single think of the match so far" in t and "20m 00s" in t for t in texts)
    assert any("B set the least time used before leaving theory in any game so far: 1m 40s (previous low 6m 40s)" in t for t in texts)
    assert any("left theory earliest so far" in t for t in texts)        # novelty ply 5 < 7


def test_streak_rose_for_second_game_in_a_row():
    gs = [game(i, D4, 5, prep=(p, 300)) for i, p in ((1, 100), (2, 200), (3, 300))]
    texts = [a["text"] for a in alerts_after(gs, DISPLAY)]
    assert "A's time used before leaving theory rose for the second game in a row (1m 40s → 3m 20s → 5m 00s)." in texts


def test_firsts_only_once():
    g1 = game(1, D4, 5)
    g2 = game(2, D4, 5, result="1-0", errors=(0, 1), trouble=(0, 3), missed=("white",))
    g3 = game(3, D4, 5, result="0-1", errors=(0, 1))
    texts2 = [a["text"] for a in alerts_after([g1, g2], DISPLAY)]
    assert "Game 2: the first decisive game of the match after 1 draw: A won." in texts2
    assert "Game 2: B's first mistake of the match (engine-classified)." in texts2
    assert any("first time B got into time trouble" in t for t in texts2)
    assert any("first time A let an opponent error go unpunished" in t for t in texts2)
    texts3 = [a["text"] for a in alerts_after([g1, g2, g3], DISPLAY)]
    assert not any("first" in t for t in texts3)


def test_history_is_per_game_in_round_order():
    h = alert_history([game(2, D4, 5), game(1, E4, 7)], DISPLAY)
    assert [x["game"] for x in h] == ["Game 1", "Game 2"]


def test_records_need_three_games_by_default():
    g = lambda n, lt: game(n, D4, 5, longest=(lt, 100))
    assert not [a for a in alerts_after([g(1, 600), g(2, 900)], DISPLAY) if a["kind"] == "record"]
    recs = [a["text"] for a in alerts_after([g(1, 600), g(2, 900), g(3, 1500)], DISPLAY) if a["kind"] == "record"]
    assert recs == ["Game 3: A set the longest single think of the match so far (x): 25m 00s (previous high 15m 00s)."]
