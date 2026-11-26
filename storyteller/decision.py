"""Deterministic description of a decision: what kinds of moves were on the
table, what had just happened, and the material situation.

These facts let the narrator explain *why* a decision may have taken long
without judging the position itself.
"""
from __future__ import annotations

import chess

PIECE_NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}


def move_character(fen: str, pv_san: list[str]) -> dict:
    """What kind of move the first move of a line is, and whether the line trades pieces."""
    board = chess.Board(fen)
    move = board.parse_san(pv_san[0])
    piece = board.piece_at(move.from_square)
    mover = board.turn
    is_capture = board.is_capture(move)
    is_castle = board.is_castling(move)
    gives_check = board.gives_check(move)
    pawn = piece.piece_type == chess.PAWN
    # retreat = a piece moving back toward its own side
    rank_from, rank_to = chess.square_rank(move.from_square), chess.square_rank(move.to_square)
    toward_home = (rank_to < rank_from) if mover == chess.WHITE else (rank_to > rank_from)
    board.push(move)
    pawn_tension = False
    if pawn:
        # the pawn now attacks an enemy pawn, or is attacked by one: it changes the structure
        attacked = [sq for sq in board.attacks(move.to_square) if board.piece_at(sq) == chess.Piece(chess.PAWN, not mover)]
        attackers = [sq for sq in board.attackers(not mover, move.to_square) if board.piece_type_at(sq) == chess.PAWN]
        pawn_tension = bool(attacked or attackers)
    # exchanges in the first 4 plies of the engine line
    b = chess.Board(fen)
    captures = 0
    for san in pv_san[:4]:
        mv = b.parse_san(san)
        captures += b.is_capture(mv)
        b.push(mv)

    kinds = []
    if is_castle:
        kinds.append("castling")
    elif is_capture:
        kinds.append(f"{PIECE_NAMES[piece.piece_type]} capture")
    elif pawn:
        kinds.append("pawn move that creates pawn tension (changes the structure)" if pawn_tension else "quiet pawn move")
    else:
        kinds.append(f"{PIECE_NAMES[piece.piece_type]} {'retreat' if toward_home else 'move'}")
    if gives_check:
        kinds.append("check")
    return {
        "kind": ", ".join(kinds),
        "piece": PIECE_NAMES[piece.piece_type],
        "is_capture": is_capture,
        "gives_check": gives_check,
        "commits_pawn_structure": pawn,
        "captures_in_first_4_plies_of_line": captures,
    }


def position_context(fen: str) -> dict:
    board = chess.Board(fen)
    count = lambda pt: len(board.pieces(pt, chess.WHITE)) + len(board.pieces(pt, chess.BLACK))
    return {
        "queens_on_board": count(chess.QUEEN) > 0,
        "pieces_left_excluding_kings_and_pawns": sum(count(pt) for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)),
        "pawns_left": count(chess.PAWN),
        "in_check": board.is_check(),
        "legal_moves": board.legal_moves.count(),
    }
