import pytest

from storyteller.match_odds import expected, game_probs, match_win, win_probability

A, B = "A", "B"


def pairings(n, results=()):
    res = dict(results)
    return [{"round": r, "white": A if r % 2 else B, "black": B if r % 2 else A,
             "white_elo": 2700, "black_elo": 2700, "result": res.get(r, "*")} for r in range(1, n + 1)]


def test_game_probs_sum_to_one_and_clamp():
    for diff in (-800, -100, 0, 100, 800):
        pw, pd, pb = game_probs(2700 + diff, 2700, 0.65, 35)
        assert pytest.approx(pw + pd + pb) == 1 and min(pw, pd, pb) >= 0
    pw, pd, pb = game_probs(2700, 2700, 0.6, 0)
    assert pytest.approx(pw) == 0.2 and pytest.approx(pb) == 0.2


def test_equal_players_no_colour_bonus_is_fifty_fifty():
    r = match_win(pairings(4), {}, A, B, {A: 2700, B: 2700}, 0.6, 0)
    assert pytest.approx(r["win"][A]) == 0.5 and pytest.approx(r["win"][B]) == 0.5


def test_one_game_left_closed_form():
    # 1 game, no draws allowed in the tie sense: tie only on a draw (prob d) -> tiebreak 50/50
    r = match_win(pairings(1), {}, A, B, {A: 2700, B: 2700}, 0.6, 0)
    assert pytest.approx(r["tiebreak"]) == 0.6
    assert pytest.approx(r["decided_in_classical"][A]) == 0.2


def test_clinched_match_is_certain():
    res = {1: "1-0", 2: "0-1", 3: "1-0"}   # A won all three (A white in odd rounds)
    r = match_win(pairings(4), res, A, B, {A: 2700, B: 2700}, 0.65, 35)
    assert pytest.approx(r["win"][A]) == 1.0


def test_higher_rated_player_is_favourite_and_series_shape():
    ps = pairings(14, [(1, "1/2-1/2"), (2, "1/2-1/2")])
    for p in ps:
        for side in ("white", "black"):
            p[f"{side}_elo"] = 2782 if p[side] == B else 2710
    out = win_probability(ps, {"draw_rate": 0.65, "draw_rate_range": [0.55, 0.75], "white_advantage_elo": 35}, [A, B], {})
    assert [s["after_game"] for s in out["series"]] == [0, 1, 2]
    s0 = out["series"][0]
    assert s0["win"][B] > 50 and pytest.approx(s0["win"][A] + s0["win"][B], abs=0.2) == 100
    lo, hi = s0["band"][A]
    assert lo <= s0["win"][A] <= hi
    assert out["series"][2]["score"] == {A: 1.0, B: 1.0}
    assert out["next_game"]["round"] == 3


def test_expected_symmetry():
    assert pytest.approx(expected(72) + expected(-72)) == 1
