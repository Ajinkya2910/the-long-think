from storyteller.events import missed_chances, prep_payoff, reactions, usual_think

SIDES = ("white", "black")


def mk(n, over=None):
    """n plies of a quiet game; `over` maps ply -> dict of overrides."""
    moves = []
    for ply in range(n):
        side = SIDES[ply % 2]
        m = {
            "ply": ply, "side": side, "label": f"{ply // 2 + 1}{'.' if side == 'white' else '...'}m{ply}",
            "clock": {"spent": 60, "remaining": 7200 - 60 * (ply // 2 + 1)},
            "in_book": ply < 10, "classification": None, "wp_loss": 0.0,
            "eval_before": {"cp": 0, "mate": None, "wp": 50.0}, "eval_after": {"cp": 0, "mate": None, "wp": 50.0},
            "top_lines": [{"san": f"best{ply}", "cp": 0, "mate": None}],
        }
        for k, v in (over or {}).get(ply, {}).items():
            m[k] = {**m[k], **v} if isinstance(v, dict) and isinstance(m.get(k), dict) else v
        moves.append(m)
    return moves


def test_usual_think_ignores_book_and_unknown():
    moves = mk(30, {20: {"clock": {"spent": None}}, 2: {"clock": {"spent": 5000}}})
    assert usual_think(moves, "white") == 60


def test_reaction_to_novelty_and_error():
    moves = mk(40, {
        13: {"in_book": False},
        14: {"clock": {"spent": 600}},                     # white's answer to the novelty
        21: {"classification": "mistake", "wp_loss": 12},  # black errs
        22: {"clock": {"spent": 300}},                     # white's answer
    })
    rs = reactions(moves, novelty_ply=13)
    assert [(r["trigger_ply"], r["response_ply"]) for r in rs] == [(13, 14), (21, 22)]
    assert rs[0]["trigger_kinds"] == ["novelty"] and rs[0]["ratio"] == 10.0
    assert rs[1]["trigger_kinds"] == ["mistake"] and rs[1]["spent"] == 300 and rs[1]["usual"] == 60


def test_prep_payoff_from_novelty_players_view():
    moves = mk(60, {
        13: {"eval_before": {"cp": 20, "mate": None, "wp": 51.8}},     # black leaves theory; white-POV +0.20
        32: {"eval_after": {"cp": -150, "mate": None, "wp": 36.5}},     # 10 moves later black is better
    })
    pp = prep_payoff(moves, 13, 7200, 10)
    assert pp["player_side"] == "black" and pp["end_ply"] == 32 and not pp["truncated"]
    assert pp["eval_before"] == -0.2 and pp["eval_after"] == 1.5
    assert pp["win_chance_change"] == round(63.5 - 48.2, 1)
    assert pp["moves_measured"] == 10


def test_prep_payoff_truncated_when_game_ends():
    pp = prep_payoff(mk(20), 13, 7200, 10)
    assert pp["truncated"] and pp["end_ply"] == 19


def test_prep_payoff_none_without_novelty():
    assert prep_payoff(mk(20), None, 7200, 10) is None


def test_missed_chance_detected_only_when_gift_returned():
    moves = mk(40, {
        20: {"wp_loss": 18, "classification": "blunder"},
        21: {"wp_loss": 12, "classification": "mistake"},   # gives back 12 of 18 -> missed
        30: {"wp_loss": 15, "classification": "blunder"},
        31: {"wp_loss": 2},                                  # punished -> not missed
    })
    mc = missed_chances(moves, min_gift=10, give_back=0.5)
    assert len(mc) == 1
    assert mc[0]["error_ply"] == 20 and mc[0]["reply_ply"] == 21
    assert mc[0]["gift"] == 18 and mc[0]["given_back"] == 12 and mc[0]["best_reply"] == "best21"


def test_small_gifts_are_ignored():
    moves = mk(40, {20: {"wp_loss": 6}, 21: {"wp_loss": 6}})
    assert missed_chances(moves, 10, 0.5) == []
