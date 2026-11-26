import chess

from storyteller.decision import move_character, position_context
from storyteller.narrative import template_reasons, ungrounded_moves


def test_pawn_tension_and_trades():
    b = chess.Board()
    for san in ["e4", "d5"]:
        b.push_san(san)
    c = move_character(b.fen(), ["exd5", "Qxd5", "Nc3", "Qa5"])
    assert c["kind"] == "pawn capture" and c["captures_in_first_4_plies_of_line"] == 2
    b2 = chess.Board()
    b2.push_san("e4")
    c2 = move_character(b2.fen(), ["d5"])
    assert "pawn tension" in c2["kind"] and c2["commits_pawn_structure"]
    assert move_character(chess.Board().fen(), ["e4"])["kind"] == "quiet pawn move"


def test_retreat_check_and_castling():
    b = chess.Board("r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 3")
    assert move_character(b.fen(), ["O-O"])["kind"] == "castling"
    assert move_character(b.fen(), ["Ba4"])["kind"] == "bishop retreat"
    chk = chess.Board("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    assert move_character(chk.fen(), ["Ra8+"])["kind"] == "rook move, check"


def test_position_context():
    p = position_context(chess.Board().fen())
    assert p["queens_on_board"] and p["pieces_left_excluding_kings_and_pawns"] == 14 and p["pawns_left"] == 16


def test_template_reasons_only_for_slow_moves():
    base = {"time_spent_seconds": 1200, "good_moves_available": 5, "good_moves_is_lower_bound": True,
            "only_move_position": False, "moves_since_leaving_book": 2, "engine_best_move_character": None, "engine_alternatives": []}
    reasons = [r["reason"] for r in template_reasons(base)]
    assert any("at least 5" in r for r in reasons) and any("2 moves earlier" in r for r in reasons)
    assert template_reasons({**base, "time_spent_seconds": 30}) == []


def test_guard_allows_previous_move_and_earlier_thinks():
    f = {"played_san": "Bb4", "engine_best_move": "Bb4", "engine_best_line": [], "engine_alternatives": [{"move": "f5"}],
         "opponent_previous_move": {"san": "b3"}, "player_earlier_thinks_over_10_min_this_game": [{"move": "12...Be7"}],
         "left_theory_with": "13...Bd7"}
    assert ungrounded_moves("After 17.b3, Gukesh (who spent long on 12...Be7 and 13...Bd7) chose Bb4 over f5.", f) == []
    assert ungrounded_moves("Nxe5 was also possible.", f) == ["Nxe5"]
