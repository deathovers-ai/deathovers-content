# DeathOvers Intelligence Engine — Data Quality Notes

This file documents known limitations and validation results for the
Cricsheet-derived data powering the Context Repository (venue_stats.json,
player_stats.json). Read this before building anything on top of player
career totals, especially anything presented as "all-time" or "career"
stats to end users.

## Data source and coverage

- Source: Cricsheet (https://cricsheet.org), version 1.2.0 JSON format
- Corpus snapshot date: matches from **2001-12-19 to 2026-07-12**
- 22,284 matches parsed successfully, 0 failures
- 370 matches withheld by Cricsheet's own policy (Afghanistan men's team /
  Afghanistan Premier League matches are excluded from their public
  dataset entirely - see https://cricsheet.org/withheld-matches)

## KNOWN LIMITATION: pre-2003 ball-by-ball coverage is thin

Cricsheet's ball-by-ball data is sparse before ~2002-2003, even though
Cricsheet's own metadata (scorecards, results) may go back further for
some formats. Ball-by-ball detail - which is what our parser needs to
compute batting/bowling stats - only becomes consistently available
from roughly 2003 onward.

**Practical effect:** any player whose international career started
before ~2002 will show meaningfully UNDERSTATED career totals in
player_stats.json, because a real chunk of their career simply isn't
represented in the underlying data - not because of any bug in the
parser or aggregation logic.

**Confirmed with a real example (July 2026 validation session):**
Jacques Kallis (international career 1995-2014) shows 7,988 combined
ODI+T20I runs and 170 wickets in our data, versus his real career
totals of ~12,245 runs and 285 wickets (source: ESPNcricinfo, Wikipedia,
cross-checked July 2026). That's roughly a 35% shortfall - traced
directly to our ODI match count for him being 132 in our data vs his
real 328 ODIs played. Our corpus only has 3 ODI matches total from 2002
and effectively starts real coverage in 2003.

**What this means for product decisions:**
- Live match commentary, current-player stats, and recent-history
  context (the actual product surface for DeathOvers) are NOT affected -
  every player we've validated with a career starting after ~2003 has
  matched real-world figures within a small, explainable margin.
- Any feature that presents "career totals" or "all-time leaderboards"
  spanning players from the 1990s-early 2000s MUST either scope itself
  to "since 2003" explicitly, or carry a visible disclaimer. Silently
  showing Kallis-style undercounted totals as if they were complete
  career figures would be actively misleading.
- If full historical coverage back to the 1990s is ever needed, that
  requires a different/supplementary data source - Cricsheet alone
  won't close this gap.

## Validation methodology and results (July 2026)

Player stats were spot-checked against live official sources (Cricbuzz
RapidAPI player profiles, ESPNcricinfo, Wikipedia, and other stat sites)
for 11 players spanning different roles, formats, eras, and genders.

| Player | Career start | Result |
|---|---|---|
| Virat Kohli | 2008 | Bowling exact match (1,252 runs, 13 wkts). Batting 98.8% match (27,990 vs ~28,326 combined) |
| Smriti Mandhana | 2013 | WPL: 35 matches exact, runs within 2 (1,025 vs 1,023), SR within 0.3 |
| Stuart Broad | 2006 | Wickets 237 vs 243 online (97.5% match) |
| James Anderson | 2002 | Wickets 268 vs 287 online (93.4% match) |
| Kevin Pietersen | 2004 | Structurally consistent (no single directly-comparable online total) |
| Hardik Pandya | 2016 | Wickets and runs both in expected range |
| Sanju Samson | 2015 | 7,123 vs 7,090 runs online (99.5% match). Bowling correctly shows zero (never bowled) |
| Josh Hazlewood | 2010 | 287 vs 293 wickets online (98% match) |
| Bhuvneshwar Kumar | 2012 | 455 vs ~520 wickets online (87.5% match, includes extra T20 leagues) |
| Abhishek Sharma | 2018 | 3,997 vs ~3,577 runs online (higher due to ongoing 2026 season not yet reflected in source) |
| **Jacques Kallis** | **1995** | **7,988 vs 12,245 runs (65% of true total) - confirmed pre-2003 gap** |

**Pattern observed:** every gap for post-2003-career players was small
(0.5-13%) and explained by one or both of:
1. Our aggregate includes domestic T20 leagues (WPL, BBL, CPL, etc.)
   that single-format online sources don't count, so our totals are
   usually slightly HIGHER than international-only figures.
2. Our Cricsheet snapshot is a few days behind live data (corpus ends
   2026-07-12), so very recent innings aren't yet reflected.

Neither of these affects data correctness - they're expected, explained
differences in scope and freshness, not errors.

## Player identity resolution

Player name variants (e.g. "P Nissanka" vs "RAP Nissanka") are merged
using Cricsheet's own `registry.people` block, which assigns a stable
ID per real player. See `registry_verification.py` and
`player_aliases.json`. Only 49 real merges exist across all 8,902
tracked names - name-pattern-based guessing (tried and abandoned earlier
in this project) produced false positives and should not be used.

## Venue name normalization

Cricsheet uses inconsistent venue name strings for the same physical
ground (e.g. "R Premadasa Stadium" / "R.Premadasa Stadium" / "R Premadasa
Stadium, Colombo" are all one venue). `context_repository.py` normalizes
these before aggregating venue stats - 884 raw venue strings collapse to
622 real, canonical venues. See `normalize_venue()` for the logic.

## Last updated

July 2026, during Sprint 0 (Epics 1-4b), following a manual validation
session cross-referencing Cricbuzz RapidAPI and web search results
against player_stats.json and venue_stats.json.
