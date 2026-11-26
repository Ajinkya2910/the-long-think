"""Opening tree: every game of the match merged into one move tree.

Each game contributes its moves up to and including its novelty (the first
move outside the masters database). If book data is missing, the first
`fallback_plies` plies are used instead. Linear runs of moves are collapsed
into segments so the tree reads like an opening book:

    1.e4 e5 2.Nf3 Nc6 3.Bb5 Nf6 ... 13...Bd7 *   (Game 1, novelty by Gukesh)
    1.d4 d5 2.Nf3 Nf6 3.Bf4 ...   11...Qd8 *   (Game 2, novelty by Sindarov)
"""
from __future__ import annotations


def _label(ply: int, san: str) -> str:
    return f"{ply // 2 + 1}{'.' if ply % 2 == 0 else '...'}{san}"


def game_line(doc: dict, fallback_plies: int = 20) -> list[dict]:
    nov = doc["opening"].get("novelty_ply")
    last = nov if nov is not None else min(fallback_plies, len(doc["moves"])) - 1
    book = {b["ply"]: b["games"] for b in doc["opening"].get("book", [])}
    return [
        {"ply": m["ply"], "san": m["san"], "label": m["label"], "master_games": book.get(m["ply"])}
        for m in doc["moves"][: last + 1]
    ]


def build_trie(docs: list[dict], fallback_plies: int = 20) -> dict:
    root = {"san": None, "ply": -1, "games": [], "children": []}
    for doc in docs:
        nov = doc["opening"].get("novelty_ply")
        node = root
        root["games"].append(doc["id"])
        line = game_line(doc, fallback_plies)
        for mv in line:
            child = next((c for c in node["children"] if c["san"] == mv["san"]), None)
            if child is None:
                child = {**mv, "games": [], "children": [], "novelties": []}
                node["children"].append(child)
            child["games"].append(doc["id"])
            if mv["master_games"] is not None:
                child["master_games"] = mv["master_games"]
            node = child
        if line and nov is not None:
            m = doc["moves"][nov]
            node["novelties"].append({
                "game_id": doc["id"],
                "round": doc.get("round"),
                "side": m["side"],
                "player": m["player"],
                "result": doc["result"],
                "ply": nov,
            })
        elif line:
            node.setdefault("ends", []).append({"game_id": doc["id"], "round": doc.get("round"), "result": doc["result"], "reason": "no book data"})
    return root


def compress(node: dict) -> list[dict]:
    """Turn the trie into segments: runs of moves without branching or novelties."""
    segments = []
    for child in node["children"]:
        moves = [child]
        cur = child
        while len(cur["children"]) == 1 and not cur["novelties"] and not cur.get("ends"):
            cur = cur["children"][0]
            moves.append(cur)
        segments.append({
            "moves": [{"ply": m["ply"], "san": m["san"], "label": m["label"], "master_games": m.get("master_games")} for m in moves],
            "games": cur["games"],
            "novelties": cur["novelties"],
            "ends": cur.get("ends", []),
            "children": compress(cur),
        })
    return segments


def opening_tree(docs: list[dict], fallback_plies: int = 20) -> dict:
    ordered = sorted(docs, key=lambda d: int(str(d.get("round") or "0").split(".")[0] or 0))
    trie = build_trie(ordered, fallback_plies)
    return {"games": trie["games"], "segments": compress(trie)}
