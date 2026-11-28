from storyteller import headlines as H


def prof(short, share, clock10, think_lo, think_hi, hard, acc=98.8):
    return {"short": short, "games": 3, "accuracy": acc, "time_share_by_phase": share,
            "accuracy_by_clock": [{"bucket": "< 10 min", "moves": clock10[1], "accuracy": clock10[0]}],
            "accuracy_by_think": [{"bucket": "< 1 min", "moves": 40, "accuracy": think_lo}, {"bucket": "> 15 min", "moves": think_hi[1], "accuracy": think_hi[0]}],
            "accuracy_hard": {"moves": hard[1], "accuracy": hard[0]}}


MID = {"opening": 13, "middlegame": 60, "endgame": 27}


def test_current_match_headlines():
    out = H.chart_headlines({"G": prof("Gukesh", MID, (99.8, 17), 99.5, (97.8, 4), (100.0, 6)),
                             "S": prof("Sindarov", MID, (98.6, 9), 99.5, (97.1, 5), (100.0, 10))})
    assert out == {"phase": "Both players spend most of their time in the middlegame",
                   "pressure": "Neither player has slipped with under 10 minutes left",
                   "think": "So far, longer thinks haven't meant more accurate moves",
                   "hard": "Both were near-perfect when only a few good moves existed"}


def test_thin_data_and_splits():
    out = H.chart_headlines({"G": prof("Gukesh", MID, (90.0, 12), 95.0, (99.0, 6), (95.0, 8)),
                             "S": prof("Sindarov", {"opening": 50, "middlegame": 30, "endgame": 20}, (98.0, 2), 99.0, (97.0, 2), (99.0, 2))})
    assert out["phase"] == "Gukesh spends most time in the middlegame, Sindarov in the opening"
    assert out["pressure"].startswith("Too few")          # Sindarov has 2 moves under 10 min
    assert out["think"].startswith("Too few") and out["hard"].startswith("Too few")
    out = H.chart_headlines({"G": prof("Gukesh", MID, (90.0, 12), 95.0, (99.0, 6), (95.0, 8)),
                             "S": prof("Sindarov", MID, (98.5, 12), 99.0, (97.0, 6), (99.0, 8))})
    assert out["pressure"].startswith("Gukesh has been less accurate")
    assert out["think"] == "Long thinks have paid off for Gukesh, not for Sindarov"
    assert out["hard"].startswith("Sindarov has handled hard positions better")


def test_prep_headline():
    assert H.prep_headline({"Gukesh": [1515, 1005, 117], "Sindarov": [317, 470, 2085]}) == "Prep time is moving in opposite directions"
    assert H.prep_headline({"Gukesh": [1515, 1005, 117], "Sindarov": [317, 470, 300]}) == "Gukesh is leaving theory faster every game"
    assert H.prep_headline({"Gukesh": [1, 2], "Sindarov": [3, 4]}).startswith("Time used")


def mv(ply, num, side, rem):
    return {"ply": ply, "move_number": num, "side": side, "label": f"{num}.x", "clock": {"remaining": rem}}


def test_game_tag_priorities():
    players = {"white": {"name": "Sindarov, Javokhir", "short": "Sindarov"}, "black": {"name": "Gukesh D", "short": "Gukesh"}}
    base = {"players": players, "result": "1/2-1/2", "summary": {"longest_think": {"ply": 0, "seconds": 600}, "novelty": {"label": "14.a3"}},
            "moves": [mv(0, 1, "white", 3000), mv(1, 39, "black", 8), mv(2, 60, "white", 900)]}
    assert H.game_tag(base) == "Gukesh down to 8 seconds"
    assert H.game_tag({**base, "result": "1-0"}) == "Sindarov won"
    calm = {**base, "moves": [mv(0, 1, "white", 3000), mv(1, 20, "black", 900)]}
    assert H.game_tag(calm) == "Drawn in 20 moves"
    calm["summary"] = {"longest_think": {"ply": 0, "seconds": 2174}, "novelty": None}
    assert H.game_tag(calm) == "Sindarov thought 36 min on one move"
