from storyteller.analysis import difficulty, rank_critical, score_moment

CC = {"top_n": 3, "min_gap_plies": 4, "time_norm_seconds": 1800, "weight_swing": 0.5, "weight_time": 0.3, "weight_difficulty": 0.2}


def mv(ply, wp_loss=0.0, spent=0, diff=0.0):
    return {"ply": ply, "wp_loss": wp_loss, "clock": {"spent": spent}, "difficulty": {"score": diff}}


def test_score_components_are_capped():
    s = score_moment(mv(0, wp_loss=50, spent=7200, diff=1.0), CC)
    assert s["swing"] == 1.0 and s["time"] == 1.0 and s["total"] == 1.0


def test_blunder_outranks_long_think():
    moves = [mv(i) for i in range(30)]
    moves[10] = mv(10, wp_loss=30)          # 0.5
    moves[20] = mv(20, spent=1800)          # 0.3
    ranked = rank_critical(moves, CC)
    assert [r["ply"] for r in ranked] == [10, 20]
    assert ranked[0]["score"]["total"] > ranked[1]["score"]["total"]


def test_min_gap_suppresses_neighbours_and_output_sorted_by_ply():
    moves = [mv(i) for i in range(40)]
    moves[20] = mv(20, wp_loss=40)
    moves[21] = mv(21, wp_loss=35)          # too close to 20
    moves[5] = mv(5, spent=1200)
    moves[35] = mv(35, diff=0.9)
    ranked = rank_critical(moves, CC)
    assert [r["ply"] for r in ranked] == [5, 20, 35]


def test_top_n_and_zero_scores_skipped():
    moves = [mv(i) for i in range(50)]
    assert rank_critical(moves, CC) == []
    for p in (0, 10, 20, 30, 40):
        moves[p] = mv(p, wp_loss=p + 1)
    assert len(rank_critical(moves, CC)) == 3


def line(cp):
    return {"cp": cp, "mate": None}


def test_difficulty_only_move():
    a = {"legal": 30, "lines": [line(0), line(-300), line(-350), line(-400), line(-500)]}
    d = difficulty(a, 0, window=4, only_gap=10)
    assert d["only_move"] and d["good_moves"] == 1 and d["score"] > 0.9


def test_difficulty_many_good_moves_is_easy():
    a = {"legal": 30, "lines": [line(20), line(15), line(10), line(5), line(0)]}
    d = difficulty(a, 0, window=4, only_gap=10)
    assert d["good_moves"] == 5 and not d["only_move"] and d["score"] < 0.1


def test_difficulty_from_black_pov():
    # black to move; white-POV cps: best for black is -300
    a = {"legal": 20, "lines": [line(-300), line(100), line(150)]}
    assert difficulty(a, 1, window=4, only_gap=10)["only_move"]


def test_forced_move_has_zero_difficulty():
    assert difficulty({"legal": 1, "lines": [line(0)]}, 0, 4, 10)["score"] == 0
