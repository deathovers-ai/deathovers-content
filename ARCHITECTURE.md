# ARCHITECTURE.md
# DeathOvers Intelligence Engine — Technical Architecture
Version: 1.0 (reflects actual implementation as of Sprint 0, July 2026)

This is the companion file to `CLAUDE.md`. That file defines how to think
and work; this file describes what actually exists — real modules, real
data shapes, real known limitations. If this file and the running code
ever disagree, the code is correct and this file is stale — update it.

---

# PIPELINE OVERVIEW

This is the real pipeline, not an aspirational one:

```
Cricsheet raw JSON (22,284 matches)
        ↓
cricsheet_parser.py       -- Cricsheet's format -> internal ball-event schema
        ↓
output/events/*.json      -- one flat event list per match (LOCAL ONLY, gitignored)
        ↓
replay_engine.py          -- ball-by-ball state reconstruction (MatchState)
        ↓
metrics_engine.py         -- facts only: runs, SR, economy, run rate, RRR
        ↓
context_repository.py     -- venue_stats.json (462 venues, phase-wise)
player_context.py         -- player_stats.json (8,878 players)
registry_verification.py  -- player_aliases.json (49 registry-confirmed merges)
        ↓
insight_engine.py         -- compares live facts against historical context,
                              WITH data-confidence guards (see below)
        ↓
match_intelligence_api.py -- get_match_insights(live_state) entrypoint
app_integration.py        -- translates real Cricbuzz API shapes -> live_state
        ↓
app.py                    -- Flask backend, live Cricbuzz polling,
                              attaches "intelligence" key to match-details response
        ↓
LiveCarousel.jsx           -- frontend, renders insights when non-empty
```

**Note on CLAUDE.md's stated pipeline** ("Analytics Engine → Metrics Engine
→ Evidence Layer → Validation Layer → LLM Explanation"): the Evidence
Layer and Validation Layer are not yet separate modules. Validation logic
currently lives inline inside `insight_engine.py` as guard functions
(`venue_data_is_reliable()`, `player_data_is_reliable()`). The LLM
Explanation layer does not exist yet — all insight text today is
template-generated in `insight_engine.py`, not AI-narrated. This is a
planned future layer (see "Planned, Not Yet Built" below), and per
CLAUDE.md's golden rule, when built it must only narrate pre-verified
facts, never generate new ones.

---

# DATA LAYER

## Source: Cricsheet

- 22,284 matches, Dec 2001 - present (corpus refreshed manually, not live)
- Format: Cricsheet JSON v1.2.0
- 370 matches withheld by Cricsheet's own policy (Afghanistan men's/APL)
- **Known limitation**: ball-by-ball coverage is thin before ~2002-2003.
  See `DATA_QUALITY_NOTES.md` for the full writeup and the Kallis case
  study that proved this (35% undercounted career stats for a
  pre-2003-debut player).

## Internal event schema (`schema/event_schema.md`)

One flat record per delivery: match_id, innings_num, over, ball_in_over,
batter, bowler, runs_batter/extras/total, extra_type, is_wicket, wickets[].
Match-level fields (venue, match_type, season) are denormalized onto every
ball row - this is a flat log optimized for sequential scanning, not a
normalized relational schema.

## Generated outputs (what's actually committed to git vs. not)

| File | Committed? | Why |
|---|---|---|
| `intelligence/raw_data/*.json` | No | 3.7GB, regenerate locally from Cricsheet |
| `intelligence/output/events/*.json` | No | Enormous (one file per match) |
| `intelligence/output/manifest.json` | No | Regenerated alongside events |
| `intelligence/output/context/venue_stats.json` | **Yes** | Small (~400KB), needed at runtime |
| `intelligence/output/context/player_stats.json` | **Yes** | ~3.8MB, needed at runtime |
| `intelligence/output/context/player_aliases.json` | **Yes** | ~4KB, registry-confirmed merges |

Render (production) only has what's in git - this is why the three
context JSON files are deliberately NOT gitignored, unlike everything
else in `output/`.

---

# THE REPLAY ENGINE (`replay_engine.py`)

`MatchState` tracks live ball-by-ball state: score, wickets, striker/
non-striker, bowler, per-batter and per-bowler running lines,
`fall_of_wickets`, `recent_balls`. `ReplayEngine` wraps this to replay a
full match or fast-forward to any point (`replay_to(innings, over, ball)`).

This is the same engine used for both historical replay (validation,
context-building) and conceptually for live matches - though live
matches currently go through `app_integration.py`'s simpler
`build_live_state()` path rather than a full `MatchState`, since live
data doesn't need ball-by-ball replay, just the current snapshot.

---

# THE METRICS ENGINE (`metrics_engine.py`)

Deliberately scoped to FACTS ONLY, per explicit design decision this
sprint: runs, wickets, overs, balls, extras, fours, sixes, dot balls,
singles/doubles/triples, strike rate, economy, current run rate,
required run rate (2nd innings only). No interpretation, no "good/bad"
labels - that's the Insight Engine's job. This mirrors CLAUDE.md's
"Golden Rule" (facts from code, language from AI) one layer earlier than
the LLM boundary: even within the deterministic code, raw computation is
kept separate from comparative/interpretive computation.

---

# CONTEXT REPOSITORY

## Venue context (`context_repository.py` -> `venue_stats.json`)

Per venue, per format (T20/ODI/IPL tracked separately): avg first-innings
score, avg wickets, phase breakdown (powerplay/middle/death - avg runs
and avg run rate per phase). 462 venues with usable data.

**Venue name normalization**: Cricsheet uses inconsistent venue strings
for the same ground (e.g. "R Premadasa Stadium" / "R.Premadasa Stadium" /
"R Premadasa Stadium, Colombo"). `normalize_venue()` collapses these -
884 raw strings -> 622 canonical venues. This same function is reused in
`match_intelligence_api.py` to bridge live Cricbuzz venue name strings
(different punctuation style, e.g. "M.Chinnaswamy Stadium") to the same
canonical keys - confirmed working via direct testing, no separate
lookup table needed.

## Player context (`player_context.py` -> `player_stats.json`)

Per player (keyed by name string): batting (runs, balls, fours, sixes,
dismissals, innings, strike_rate, average), bowling (runs, balls,
wickets, innings, economy, average), plus `earliest_match_date` and
`latest_match_date` - the latter two fields exist specifically to power
the data-confidence guard in the Insight Engine (see below).

## Player identity resolution (`registry_verification.py`)

**Important design history, worth preserving**: an earlier attempt used
name-pattern matching (e.g. "R Sharma" could be short for "RG Sharma")
to guess at merges. This produced 235 candidate pairs, walked through
manually with apparent confidence - and was WRONG. Cross-checking against
Cricsheet's own `registry.people` block (a real per-player ID in the raw
match data) showed NONE of the "confident" pattern-matched pairs actually
shared a registry ID. The correct approach, now implemented: build
name->ID->name mappings from the registry across the full corpus, and
only merge names that provably share an ID. Result: 49 real merges out
of 8,902 tracked names - all legitimate (marriage name changes, corrected
transliterations), not initials-shorthand guesses.

**Lesson embedded in CLAUDE.md's principles**: "Never invent... trust
database... historical truth overrides model memory" - this incident is
the concrete case study for why that rule exists.

---

# THE INSIGHT ENGINE (`insight_engine.py`)

This is the Validation Layer, in practice (see note above about it not
being formally separated from Insight generation yet).

## Hard rule: DATA_CONFIDENCE_CUTOFF

Any player whose earliest recorded match is before 2005-01-01 is
excluded from comparative insights - refused, not caveated. This is
wider than the actual ~2003 data-thinness boundary, deliberately: a
player's EARLIEST RECORDED match cannot distinguish "debuted in 2003"
from "career started earlier, Cricsheet just doesn't have the early
years" (see Kallis case in DATA_QUALITY_NOTES.md). The wider margin
trades some false refusals for zero false inclusions.

**This guard was caught failing its own self-test once already** (the
initial 2003-01-01 cutoff let Kallis through, since his earliest
*recorded* match happened to be Feb 2003). Caught via the module's own
`__main__` test block before it shipped. Any future change to this
guard MUST re-run that same test.

## Significance threshold

10% minimum deviation before an insight is generated at all. An engine
that comments on every trivial wobble is noise, not intelligence.
Silence is a valid, correct output.

## Pace-adjusted comparison (not flat average)

`venue_score_insight` compares a live score against a phase-weighted
"on-pace" projection for that exact point in the innings, not the flat
full-innings average. This was a real bug, found and fixed via live
production data: a 6-over score at Edgbaston was flagged as "73.6% below
average" purely because comparing an incomplete innings to a
full-innings average is always misleading early on. Fixed by projecting
expected score-so-far from the venue's own powerplay/middle/death phase
rates. Falls back to the flat average only when the innings is
essentially complete.

## Insight types implemented

- `venue_score_insight` - live score vs. pace-adjusted venue baseline
- `venue_phase_insight` - live phase run rate vs. venue's historical phase rate
- `player_form_insight` - live strike rate vs. career strike rate (guarded by DATA_CONFIDENCE_CUTOFF)

## Insight types planned, not yet built

- Collapse detection (N wickets in M overs) - format-relative threshold,
  not venue-relative (see design discussion, Sprint 0 planning)
- Partnership/recovery detection (50+ run partnerships, especially
  following a detected collapse)
- AI narration layer (turns structured insight objects into flowing
  prose) - explicitly scoped to narrate ONLY pre-verified facts from the
  Insight Engine, never to generate new comparisons itself

---

# LIVE DATA BRIDGE

## Real Cricbuzz API shapes (verified against actual RapidAPI responses,
## not assumed from public docs - an earlier draft of this integration
## guessed wrong field names and would have silently produced zero
## player insights forever)

`miniscore.batsmanstriker` / `batsmannonstriker`: {name, runs, balls,
fours, sixes, strkrate, ...}. `miniscore.inningsscores.inningsscore`:
list of {inningsid, runs, wickets, overs, target, ...}.

**Confirmed real, intermittent failure mode**: `miniscore` can come back
`None` from Cricbuzz even during a live match with an active innings
(confirmed on both a Major League Cricket match and a full England-India
ODI at Lord's). `app.py`'s `_shape_match_details_from_cricbuzz` already
had a fallback for the scoreboard display (deriving score/overs from the
most recent `oversep` block in commentary instead). The Insight Engine
did NOT initially share this fallback - `_attach_intelligence` now
synthesizes a minimal miniscore-shaped dict from the already-resolved
`shaped["innings1"/"innings2"]` when real miniscore lacks usable score
data, tagging the result `score_source: "commentary_fallback"` so this
is always distinguishable from a genuine miniscore-backed insight.

## Pagination / commentary backfill

Cricbuzz's `/comm` endpoint only returns a recent window per call by
default. A `tms` (timestamp) query parameter enables backward pagination
- confirmed working via direct playground testing before implementation.
`_backfill_full_commentary` paginates back to ball 1 of an innings, but
ONLY on the first fetch per match/innings (tracked via
`backfilled_innings` in the detail cache) - capped at `MAX_BACKFILL_PAGES`
(8) and a quota-fraction safety limit, to protect the shared RapidAPI
daily call budget from one match's history backfill starving every other
match's live updates.

## Quota protection

Three-tier interval scheduling in `_background_loop`:
- Per-match viewer tracking (`_last_viewed`): a match only gets
  background-refreshed if someone requested its detail page within the
  last `VIEWER_ACTIVE_WINDOW_SECONDS` (90s) - fixes the confirmed real
  issue of quota being consumed by matches nobody is actively watching.
- Site-wide activity tracking (`_last_site_activity`): if the whole site
  has had zero requests recently, the carousel refresh backs off to
  `SITE_IDLE_BACKOFF_SECONDS` (1hr) regardless of whether some match is
  live somewhere in the world.
- Existing hot/warm/cold tiers (death-overs detection, wicket-in-recent-
  ball-tracker) still apply on top of the above for matches that DO have
  an active viewer.

---

# FORMAT/PHASE BOUNDARIES (kept in sync across 3 files - fragile, worth consolidating)

T20-like: powerplay 0-6 overs, middle 6-15, death 15-20.
ODI-like: powerplay 0-10, middle 10-40, death 40-50.

Currently duplicated in `context_repository.py` (PHASE_BOUNDARIES),
`match_intelligence_api.py` (determine_phase), and
`insight_engine.py` (_projected_score_at_point's `bounds`). If these
three definitions ever drift apart, venue context and live comparisons
will silently disagree. **Improvement candidate**: extract to one shared
constant, imported by all three - flagged here rather than fixed
immediately, since CLAUDE.md prefers surgical changes over
speculative refactors when nothing is currently broken.

---

# VALIDATION HISTORY (evidence this architecture actually works)

Cross-checked against live Cricbuzz/ESPNcricinfo data for 12 players
(Kohli, Mandhana, Broad, Anderson, Pietersen, Pandya, Samson, Hazlewood,
Bhuvneshwar, Abhishek Sharma - all within 0.5-13% of official figures;
Kallis - confirmed 35% gap, root-caused to pre-2003 coverage, not a bug).

Real-match projection validated: West Indies vs New Zealand, Kensington
Oval, July 2026 - projected final score range 180-190 runs (using venue
phase rates + a stated, non-guaranteed wicket-in-hand adjustment),
actual final score 188. Within range, 2 runs from the projection midpoint.

---

# KNOWN GAPS / FUTURE WORK

1. AI narration layer - not built (see above)
2. Collapse/partnership detection - not built (see above)
3. Phase boundary constants duplicated across 3 files
4. Evidence Layer / Validation Layer not formally separated from
   Insight Engine - works correctly today but doesn't structurally match
   CLAUDE.md's stated pipeline diagram
5. Venue-relative (vs. format-relative) thresholds for future pattern
   detection would need new aggregation work in context_repository.py
