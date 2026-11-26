"""Match win probability from ratings, colours and results so far.

Model (deliberately simple and fully stated on the site):
* Each game: White's expected score E from the Elo formula, using both FIDE
  ratings plus a fixed bonus for having White.
* A fixed draw rate D: P(White wins) = E - D/2, P(Black wins) = 1 - E - D/2
  (clamped at 0 for very lopsided pairings).
* Exact calculation over every remaining game (no simulation). After all
  scheduled games, the higher score wins; a tie goes to tiebreaks, which the
  higher-rated player wins with probability equal to their Elo expected score.
* The band shows the same calculation with the low and high draw rates.
"""
from __future__ import annotations


def expected(diff: float) -> float:
    return 1 / (1 + 10 ** (-diff / 400))


def game_probs(white_elo: float, black_elo: float, draw_rate: float, white_adv: float) -> tuple[float, float, float]:
    """(P white wins, P draw, P black wins)."""
    e = expected(white_elo + white_adv - black_elo)
    pw, pb, pd = e - draw_rate / 2, 1 - e - draw_rate / 2, draw_rate
    if pw < 0:
        pw, pd, pb = 0.0, 2 * e, 1 - 2 * e
    elif pb < 0:
        pb, pd, pw = 0.0, 2 * (1 - e), 1 - 2 * (1 - e)
    return pw, pd, pb


def match_win(pairings: list[dict], results: dict[int, str], a: str, b: str, ratings: dict[str, float],
              draw_rate: float, white_adv: float) -> dict:
    """P(a wins), P(b wins), P(tiebreak) given known `results` {round: '1-0'|'0-1'|'1/2-1/2'}.

    Scores are tracked in half-points for player `a`.
    """
    dist = {0: 1.0}  # a's half-points -> probability
    for p in pairings:
        rnd = p["round"]
        a_white = p["white"] == a
        res = results.get(rnd)
        if res in ("1-0", "0-1", "1/2-1/2"):
            a_pts = {"1-0": 2 if a_white else 0, "0-1": 0 if a_white else 2, "1/2-1/2": 1}[res]
            dist = {s + a_pts: q for s, q in dist.items()}
            continue
        pw, pd, pbk = game_probs(ratings[p["white"]], ratings[p["black"]], draw_rate, white_adv)
        a_win, a_loss = (pw, pbk) if a_white else (pbk, pw)
        new: dict[int, float] = {}
        for s, q in dist.items():
            for d, pr in ((2, a_win), (1, pd), (0, a_loss)):
                if pr:
                    new[s + d] = new.get(s + d, 0.0) + q * pr
        dist = new
    total_half = 2 * len(pairings)
    tie = total_half // 2 if total_half % 2 == 0 else None
    p_a = sum(q for s, q in dist.items() if s * 2 > total_half)
    p_b = sum(q for s, q in dist.items() if s * 2 < total_half)
    p_tie = dist.get(tie, 0.0) if tie is not None else 0.0
    tb_a = expected(ratings[a] - ratings[b])
    return {
        "win": {a: p_a + p_tie * tb_a, b: p_b + p_tie * (1 - tb_a)},
        "decided_in_classical": {a: p_a, b: p_b},
        "tiebreak": p_tie,
    }


def win_probability(pairings: list[dict], cfg: dict, players: list[str], display: dict) -> dict | None:
    """Series of match-win probabilities before game 1 and after each finished game."""
    if not pairings:
        return None
    a, b = players
    ratings: dict[str, float] = {}
    for p in pairings:
        for side in ("white", "black"):
            if p.get(f"{side}_elo"):
                ratings[p[side]] = float(p[f"{side}_elo"])
    if a not in ratings or b not in ratings:
        return None
    pairings = sorted(pairings, key=lambda p: p["round"])
    finished = [p for p in pairings if p.get("result") in ("1-0", "0-1", "1/2-1/2")]
    d, lo, hi = float(cfg["draw_rate"]), *map(float, cfg["draw_rate_range"])
    adv = float(cfg["white_advantage_elo"])
    short = lambda n: display.get(n, {}).get("short", n)

    series = []
    score = {a: 0.0, b: 0.0}
    for k in range(len(finished) + 1):
        known = {p["round"]: p["result"] for p in finished[:k]}
        if k:
            p = finished[k - 1]
            r = p["result"]
            score[p["white"]] += {"1-0": 1, "0-1": 0, "1/2-1/2": 0.5}[r]
            score[p["black"]] += {"1-0": 0, "0-1": 1, "1/2-1/2": 0.5}[r]
        base = match_win(pairings, known, a, b, ratings, d, adv)
        band = [match_win(pairings, known, a, b, ratings, x, adv)["win"][a] for x in (lo, hi)]
        series.append({
            "after_game": k,
            "label": "Before Game 1" if k == 0 else f"After Game {finished[k - 1]['round']}",
            "result": finished[k - 1]["result"] if k else None,
            "score": dict(score),
            "win": {n: round(100 * v, 1) for n, v in base["win"].items()},
            "tiebreak": round(100 * base["tiebreak"], 1),
            "band": {a: [round(100 * min(band), 1), round(100 * max(band), 1)]},
        })

    nxt = next((p for p in pairings if p.get("result") not in ("1-0", "0-1", "1/2-1/2")), None)
    next_game = None
    if nxt:
        pw, pd, pbk = game_probs(ratings[nxt["white"]], ratings[nxt["black"]], d, adv)
        next_game = {"round": nxt["round"], "white": nxt["white"], "black": nxt["black"],
                     "white_win": round(100 * pw, 1), "draw": round(100 * pd, 1), "black_win": round(100 * pbk, 1)}
    return {
        "players": [a, b],
        "games": len(pairings),
        "ratings": ratings,
        "assumptions": {
            "draw_rate": d, "draw_rate_range": [lo, hi], "white_advantage_elo": adv,
            "tiebreak": "higher-rated player wins tiebreaks with their Elo expected score",
            "text": (f"Each game uses the players' FIDE ratings ({short(a)} {ratings[a]:.0f}, {short(b)} {ratings[b]:.0f}), "
                     f"a {adv:.0f}-point bonus for White and a {d:.0%} draw rate. A 7–7 tie goes to tiebreaks. "
                     f"The band shows draw rates from {lo:.0%} to {hi:.0%}."),
        },
        "series": series,
        "next_game": next_game,
    }
