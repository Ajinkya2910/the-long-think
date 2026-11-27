# The Long Think

A pipeline and static website that turn World Championship games (WCC 2026, Gukesh vs Sindarov) into visual stories:
who was better when, where each player spent their clock, where opening preparation ended, the critical moments,
and an explanation of each moment written for casual fans.

**Ground rule:** the language model never judges chess. Every number comes from Stockfish, the broadcast clocks
or the Lichess masters database. The narrator only restates those facts, and its output is checked: any move it mentions
must appear in the facts it was given, or the pipeline falls back to a deterministic template. The facts behind every
card are shown on the page ("show facts").

```
Lichess broadcast PGN ──► ingest ──► engine pass (Stockfish, multi-PV, cached)
                                 ├─► clock pass (time spent, increments, arbiter adjustments)
                                 ├─► opening pass (masters explorer → novelty)
                                 └─► difficulty → critical moments → narrative (template or Claude)
                                                     │
                       web/data/games/<id>.json + web/data/match.json ──► static site (web/)
```

## Quick start

```bash
# 1. Stockfish
brew install stockfish            # macOS
sudo apt install stockfish        # Debian/Ubuntu (binary at /usr/games/stockfish → set STOCKFISH_PATH)

# 2. Python env (Python 3.11+)
uv venv && uv pip install -e ".[dev]"     # or: python -m venv .venv && pip install -e ".[dev]"

# 3. Run: fetch every played round of the broadcast and analyse it
.venv/bin/python -m storyteller run

# 4. View the site
cd web && python3 -m http.server 8000     # open http://localhost:8000
```

The first run of a game takes about 6 minutes at depth 20 on an M-series Mac. Engine results, explorer lookups and
narratives are cached in `data/cache/cache.sqlite`, so later runs take seconds.

### Analysing a new game

New rounds appear in the broadcast automatically. Just re-run:

```bash
.venv/bin/python -m storyteller run                 # picks up newly finished rounds
.venv/bin/python -m storyteller run --game game-02  # re-analyse only game 2, keep the rest
.venv/bin/python -m storyteller run --refresh       # force re-download of round PGNs
.venv/bin/python -m storyteller run --pgn some.pgn  # any local PGN (with %clk comments for clock data)
.venv/bin/python -m storyteller run --depth 24      # deeper engine pass (new cache entries)
```

### Docker

```bash
docker compose run --rm pipeline          # runs the pipeline; data/ and web/data are volumes
docker compose up web                     # serves the site on http://localhost:8080
```

### Claude narratives (optional)

Set `ANTHROPIC_API_KEY` (see `.env.example`). Each critical moment's fact sheet is sent as JSON to `claude-opus-5-5`
with structured output (headline, explanation, `facts_used`). Server-side refusal fallbacks are enabled.
Results are cached by a hash of the facts, so you pay once per moment. Without a key, the template narrator is used.

## Configuration (`config.toml`)

| Section | What it controls |
|---|---|
| `[match]` | broadcast id, player display names and colour slots |
| `[time_control]` | periods / increment. The live PGN header is inconsistent between rounds, so config wins unless `prefer_pgn_header = true` |
| `[engine]` | Stockfish path, depth, multipv (5 lines are analysed, the top 3 are exported), threads, hash |
| `[clock]` | long-think threshold (15 min) and each player's top-N thinks |
| `[difficulty]` | "good move" window and "only move" gap, in win% points; discount for recaptures / check evasions |
| `[classification]` | inaccuracy / mistake / blunder thresholds (win% lost, Lichess-style) |
| `[critical]` | number of moments, minimum spacing, weights for eval swing / time / difficulty, novelty bonus |
| `[patterns]` | prep-payoff horizon, missed-chance thresholds, games needed before records are reported |
| `[match_odds]` | draw rate (and range for the band), White bonus in rating points |
| `[crowd]` | YouTube search text, videos per game, comments per video, labelling model and batch size |
| `[narrative]` | on/off, model, effort |

Secrets come only from env vars or `.env`: `ANTHROPIC_API_KEY`, `YOUTUBE_API_KEY`, `LICHESS_TOKEN`, plus `STOCKFISH_PATH` and `ENGINE_DEPTH` overrides.

## How things are computed

- **Clock math** (`storyteller/timecontrol.py`): `%clk` is the mover's time after pressing the clock.
  `spent = previous clock − clock + increment(move) + period bonus(move)`. A negative value means time was added
  outside the rules (in Game 1, about 2 minutes appeared on Gukesh's clock at move 37). These are reported as
  `clock.adjustment`, never as negative thinks.
- **Win chances / accuracy**: Lichess's published curves. "Win chance lost" is from the mover's point of view,
  and is 0 when the played move is the engine's first choice.
- **Opening**: the first move not found in the Lichess masters database is the *novelty*. Moves before it are "book".
- **Difficulty** (0–1): half "how few good moves exist" (from 5 engine lines), half "how costly the second-best move is".
  Forced moves score 0. Recaptures and check evasions are discounted.
- **Critical moments**: `0.5·swing + 0.3·time + 0.2·difficulty (+0.15 for the novelty)`, top 5, at least 4 plies apart.
- **Reaction time** (`storyteller/events.py`): seconds spent on the move right after the opponent's novelty or classified
  error, compared with that player's median non-book think in the same game.
- **Prep payoff**: evaluation, winning chances and both clocks just before the novelty vs 10 full moves later
  (or the last move, if the game ends sooner), from the side that left theory.
- **Missed chances**: the opponent's move hands over at least 10 winning-chance points, and the reply gives back
  at least half of them. Thresholds are in `[patterns]`.
- **Opening tree** (`storyteller/opening_tree.py`): every game merged into one move tree up to its novelty;
  shared runs of moves are collapsed into single rows.
- **Insight alerts** (`storyteller/alerts.py`): after each game, what became true with that game: *records*
  (a new high or low for a player metric, from game 3 on), *streaks* (a metric rose or fell in each of the
  last 3+ games) and *firsts* (first decisive game, first mistake, first missed chance, first time trouble).
- **Match win probability** (`storyteller/match_odds.py`): each game's win/draw/loss odds from both FIDE ratings,
  a bonus for White and a fixed draw rate; an exact calculation over all remaining games (first to 7.5, a 7–7 tie
  goes to tiebreaks) gives each player's chance after every game. The shaded band uses the low and high draw
  rates from `[match_odds]`. It's a rating model, not the engine's opinion of the games.
- **Crowd mood** (`storyteller/crowd.py`, optional): for each game, the YouTube Data API finds recap videos published
  within 3 days of the round and reads their top comments (no usernames kept). Claude Haiku labels each comment
  (who it backs, tone toward each player, exciting/boring, opinions on specific moves); moves are checked against
  the game. Only counts are published, plus "engine vs crowd" for moves with 3+ opinions. Needs `YOUTUBE_API_KEY`;
  raw comments stay in the local cache. `--refresh-crowd` re-fetches.
- **Phases**: opening = book moves; endgame = 6 or fewer pieces besides kings and pawns; middlegame otherwise.

## Project layout

```
config.toml              all tunables
storyteller/             pipeline (ingest, engine, opening, timecontrol, analysis, narrative, patterns, build, cli)
schema/game.schema.json  output contract for web/data/games/*.json (validated in tests)
tests/                   clock math, critical-moment ranking, difficulty, grounding guard, schema
web/                     static site: index.html (match + pattern finder), game.html (game story)
web/vendor/chessground   vendored board (GPL-3.0, see its LICENSE)
docs/IDEAS.md            pattern-finder roadmap
```

## Tests

```bash
.venv/bin/pytest
```

## Deploying the site

`web/` is a plain static folder. Run the pipeline, then publish `web/` to GitHub Pages, Netlify, Cloudflare Pages
or any static host. A scheduled CI job (for example, nightly during the match) can run the pipeline and redeploy.

## Notes and limits

- The engine cache is keyed by FEN, depth and multipv, not by engine version. Delete `data/cache` after upgrading Stockfish.
- Accuracy numbers in a 0.00 draw cluster near 100%. Patterns become meaningful as more games come in.
- Phase 3+ (Maia human-likeness, player-history "out of character" flags) is not built yet; see `docs/IDEAS.md`.
