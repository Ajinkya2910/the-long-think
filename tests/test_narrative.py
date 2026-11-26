from storyteller.narrative import pronouns_used, template, ungrounded_moves

FACTS = {
    "move": "17...Bb4", "played_san": "Bb4", "player": "Gukesh", "opponent": "Sindarov", "color": "black",
    "phase": "middlegame", "time_spent": "36m 14s", "time_spent_seconds": 2174, "think_rank_for_player": 1,
    "player_clock_after": "28m 40s", "opponent_clock": "1h 18m", "eval_before_from_player_view_pawns": -0.39,
    "eval_after_from_player_view_pawns": -0.36, "player_win_chance_before_pct": 46.4, "player_win_chance_after_pct": 46.7,
    "win_chance_lost_pct": 0.0, "classification": "good or best move", "engine_rank_of_played_move": 1,
    "engine_best_move": "Bb4", "engine_best_line": ["Bb4", "Re2", "h6"], "engine_alternatives": [{"move": "c5", "eval_from_player_view_pawns": -0.5}],
    "good_moves_available": 2, "only_move_position": False, "difficulty_0_to_1": 0.3, "in_opening_book": False,
    "is_novelty": False, "moves_since_leaving_book": 4, "clock_adjustment_seconds": None,
}


def test_grounding_guard_flags_invented_moves():
    assert ungrounded_moves("After Bb4 and Re2, black could try Nxe5 or O-O.", FACTS) == ["Nxe5", "O-O"]


def test_grounding_guard_accepts_known_moves_with_numbers():
    assert ungrounded_moves("17...Bb4 was the engine's pick; c5 was close.", FACTS) == []


def test_template_mentions_only_facts():
    t = template(FACTS)
    assert t["source"] == "template"
    assert ungrounded_moves(t["text"], FACTS) == []
    assert "36m 14s" in t["text"]


def test_bare_square_allowed_only_if_a_fact_move_lands_there():
    assert ungrounded_moves("The bishop settled on b4.", FACTS) == []        # Bb4 lands on b4
    assert ungrounded_moves("Then h4 would follow.", FACTS) == ["h4"]          # no fact move lands on h4


def test_pronoun_detector():
    assert pronouns_used({"headline": "x", "text": "Gukesh used his time", "likely_reasons": [{"reason": "He was short"}]}) == ["he", "his"]
    assert pronouns_used({"headline": "x", "text": "The theme: hero and herring", "likely_reasons": []}) == []
    assert pronouns_used(template(FACTS)) == []
