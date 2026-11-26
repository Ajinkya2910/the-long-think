# Pattern finder: ideas and roadmap

Already built: per-game eval / time / clock charts, novelty detection, critical moments, fact-checked narratives,
cross-game player profiles (time by phase, accuracy vs clock, accuracy vs think length, hard vs easy positions),
auto-generated insights, **reaction time to surprises**, **prep payoff**, **missed chances**, the **opening tree**, **insight alerts**, and the **Moves map** scatter (every move, any two axes, filters, click-through).

Everything below follows the same rule: compute it deterministically first, then let the UI or the narrator describe it.

## 1. Time and psychology (the clock is the richest human signal)
- **Think-then-blunder detector**: does accuracy drop on the move *after* a long think (relief / fatigue)?
- **Reaction time to surprises**: time spent on the move right after the opponent's novelty or inaccuracy.
  Fast = prepared or calm, slow = surprised.
- **Clock-lead timeline**: who was ahead on the clock at each move, and whether that lead turned into eval later.
- **Time-trouble map**: moves 30–40 with < 5 min left: accuracy, and how often the opponent "plays on the clock"
  (moves faster when the other side is short).
- **Pace fingerprint**: each player's median think by move-number band; spot deviations game to game.
- **"Comfort index"**: quick moves in high-difficulty positions = deep understanding or prep; slow moves in easy positions = doubt.

## 2. Preparation
- **Prep depth per game and colour**: novelty ply, who deviated, eval at the novelty, time used before it.
- **Prep payoff**: eval change and clock gap 10 moves after the novelty. Did the prepared side gain anything?
- **Repertoire tree across the match**: one tree of all openings played, coloured by result and by who left theory.
- **Database rarity**: "this position had 2 master games", a rarity score per move (log of game counts).

## 3. Decision quality
- **Missed chances**: opponent errs, then the mover fails to punish (eval swing back).
- **Practical vs engine-best**: rank the played move in a human-move model (Maia) vs the engine (Phase 3).
  "Engine says Rd2, but most humans at 2700 play Nc3."
- **Complexity tolerance**: accuracy in "only move" positions, per player, across games.
- **Conversion / defence**: from +1.5 or better, how often does the player convert? From −1.5, how often hold?
- **Symmetry**: do they play differently with White and Black (time, risk, accuracy)?

## 4. Style ("out of character")
- From each player's past classical games: average material imbalance, how often they trade queens,
  pawn-structure types, castling choices, aggression (checks/captures per move). Flag match moves far from their norm.
- **Risk appetite**: how often they choose the engine's 2nd or 3rd line when it's within 0.2 but sharper
  (spread of the top 3 lines).

## 5. Interaction (making "everyone can analyse" real)
- Shareable deep links (already: `game.html?id=game-01&ply=34`). Add "copy link to this moment".
- **Compare view**: two games side by side, with time charts aligned by move number.
- **Ask-the-data box**: a natural-language question becomes a filter over the move table
  ("long thinks in the endgame by Gukesh"). Claude writes the filter, and the numbers come from data, never from the model.
- **Pattern alerts during the match**: after each new game, recompute the insights and highlight what changed
  ("Sindarov's average time before leaving theory rose for the third game in a row").
- Hindi / Marathi narration of the same fact sheets (Phase 4).
- Embeddable card images per critical moment for social sharing.

## 6. Robustness
- Engine version in the cache key; depth/time sweeps to report evaluation stability.
- Show "eval confidence" when the top-2 lines swap between depths.
- Cross-check broadcast `%eval` against the local engine and flag big disagreements.
