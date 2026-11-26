from storyteller.timecontrol import Period, TimeControl, compute_spent, parse_pgn_header

WCC = TimeControl((Period(40, 7200), Period(None, 1800)), increment=30, increment_from_move=41)


def plies(white, black):
    """Interleave per-player clock lists into ply order."""
    out = []
    for i in range(max(len(white), len(black))):
        if i < len(white):
            out.append(white[i])
        if i < len(black):
            out.append(black[i])
    return out


def test_first_move_spent_from_base():
    r = compute_spent([7190, 7192], WCC)
    assert [x.spent for x in r] == [10, 8]


def test_no_increment_before_move_41():
    r = compute_spent(plies([7100, 7000], [7200, 7150]), WCC)
    assert [x.spent for x in r] == [100, 0, 100, 50]


def test_bonus_after_move_40_and_increment_from_41():
    # white: clock 600 after move 39, 500 after move 40 (thought 100 s, +1800 bonus => 2300),
    # move 41: thought 60 s, +30 inc => 2270
    w = [7200 - i for i in range(1, 39)] + [600, 2300, 2270]
    b = [7200] * 41
    r = compute_spent(plies(w, b), WCC)
    white = r[0::2]
    assert white[39].spent == 100          # move 40
    assert white[40].spent == 60           # move 41
    assert white[40].remaining == 2270


def test_clock_increase_flagged_as_adjustment():
    # 37... clock went from 4:40 to 6:38 with no increment due: arbiter award, not a negative think
    w = [7000] * 37
    b = [7000] * 35 + [280, 398]
    r = compute_spent(plies(w, b), WCC)
    black37 = r[73]
    assert black37.spent is None
    assert black37.adjustment == 118
    assert "clock_adjustment" in black37.flags


def test_missing_clock():
    r = compute_spent([7190, None, 7100, 7000], WCC)
    assert r[1].spent is None and "missing_clock" in r[1].flags
    assert r[3].spent is None  # previous black clock unknown


def test_parse_pgn_header_multi_period():
    tc = parse_pgn_header("40/7200:20/3600:900+30")
    assert [p.seconds for p in tc.periods] == [7200, 3600, 900]
    assert tc.increment == 30 and tc.increment_from_move == 61
    assert tc.bonus_after(40) == 3600 and tc.bonus_after(60) == 900 and tc.bonus_after(41) == 0


def test_parse_pgn_header_rejects_free_text():
    assert parse_pgn_header("120'/40m + 30'/end, 30/move from move 41") is None
    assert parse_pgn_header("?") is None


def test_parse_simple_increment():
    tc = parse_pgn_header("5400+30")
    assert tc.base == 5400 and tc.increment == 30 and tc.increment_from_move == 1


def test_dotenv_loading(tmp_path, monkeypatch):
    from storyteller.config import load_dotenv
    env = tmp_path / ".env"
    env.write_text('ANTHROPIC_API_KEY=   # empty values are ignored\nLT_TEST_A="abc"  # comment\nLT_TEST_B=keep\n')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LT_TEST_B", "from-shell")
    load_dotenv(env)
    import os
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert os.environ["LT_TEST_A"] == "abc"
    assert os.environ["LT_TEST_B"] == "from-shell"   # real env wins
    monkeypatch.delenv("LT_TEST_A")
