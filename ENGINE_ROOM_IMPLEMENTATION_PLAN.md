# DeathOvers AI Engine Room — Gap Analysis & Implementation Plan

**Source:** `DeathOvers_AI_Engine_Room_Roadmap_2026-2027.pdf` (v1.0, 28 Jul 2026)  
**Evaluated against:** this repo as of Aug 2026 (`ARCHITECTURE.md` + live code)  
**Verdict:** The roadmap direction is right. Its inventory is stale. Chase Engine, situation detection, weather/dew, projections, Match Room, and Tactical Read already exist and must reshape priority order.

---

## 1. Plan evaluation (honest)

### What the roadmap gets right
- Cricsheet boundary is correctly stated: WHO / WHAT / WHEN only — no HOW / WHY.
- Golden Rule (facts from code, language from AI) matches the product.
- F01–F04 foundation items are real debt, already flagged in `ARCHITECTURE.md`.
- Monetization (F13–F15) correctly comes last; F15 needs legal sign-off before any build.

### What the roadmap gets wrong or undercounts
| Claim in PDF | Reality in repo |
|---|---|
| “Live-match insight panel” starting point | Full Match Room + Tactical Read (Venue / Tactical / Innings+Chase) already shipped |
| Collapse / partnership “planned, not built” | Built in `insight_engine.py` (`collapse`, `momentum`, `pressure`, `partnership`) + live commentary derivation in `app.py` |
| Weather “exists but isn’t integrated” | `weather_service.py` + dew risk attached in `app.py`; surfaced in Match Room + Tactical Read Venue tab |
| No chase intelligence called out as done | Full Chase Engine stack: snapshots, cohort, compact index, live bridge, runtime policy, UI |
| Player context = career only (implies nothing else) | Correct for form windows / venue / phase — still career aggregates only |
| “70% of the way” | Closer on **product surface**; farther on **F05/F06/F08 depth**. Treat “70%” as marketing, not a build metric |

### Architectural risks the PDF underweights
1. **Phase boundary drift** — still duplicated across `context_repository.py`, `match_intelligence_api.py`, `insight_engine.py`. Silent integrity bug waiting to happen.
2. **`ARCHITECTURE.md` is stale** — lists collapse/partnership/AI as gaps while collapse/partnership already ship. Keep docs honest before adding features.
3. **Chase Engine vs Monte Carlo (F05)** — we already answer “are they on historical chase pace?” Win probability is additive, not a replacement. Do not rebuild chase as Monte Carlo.
4. **LLM narration (F08) before richer facts (F04/F06)** — narration on thin insights produces polished emptiness. Enrich facts first.

---

## 2. Capability matrix (have / partial / need)

Legend: **HAVE** = production-usable · **PARTIAL** = code exists, incomplete vs roadmap · **NEED** = not built

| ID | Feature | Status | Evidence / gap |
|---|---|---|---|
| — | Cricsheet → events → replay → metrics → context → insights → `app.py` | **HAVE** | Full pipeline in `intelligence/parser/` |
| — | Venue stats (462 venues, phase breakdown, chase phase) | **HAVE** | `venue_stats.json`; chase_phase on 684 venue/format blocks |
| — | Player career stats + registry merges | **HAVE** | `player_stats.json` (~8.9k), `player_aliases.json` |
| — | Live Cricbuzz bridge + quota/backfill | **HAVE** | `app.py`, `app_integration.py` |
| — | Match Room UI | **HAVE** | `MatchRoom.jsx` — live state, chase signal, venue, tactical feed |
| — | Tactical Read (3 tabs) | **HAVE** | `TacticalSheetLive.jsx` — Venue Record / Tactical Read / Innings Engine (+ Chase) |
| — | Chase Engine | **HAVE** | `chase_*`, `compact_chase_engine`, `live_chase_bridge`, index gzip |
| — | Situation detection | **HAVE** | collapse / momentum / pressure / partnership in `insight_engine.py` |
| — | Score + chase projections | **HAVE** | `projection_insight`, `chase_projection_insight` |
| — | Weather + dew badge | **PARTIAL** | Fetched + shown; **not** wired into projections / win models (F09) |
| F01 | Phase constants consolidation | **NEED** | Still 3 copies |
| F02 | `validation_engine.py` extraction | **NEED** | Guards still live inside `insight_engine.py` |
| F03 | Data freshness dashboard | **NEED** | No `generated_at` on context JSONs; no UI badge |
| F04 | Player form / venue / phase stats | **NEED** | Career aggregates only today |
| F05 | Win probability (Monte Carlo) | **NEED** | Chase cohort ≠ ball-by-ball WP |
| F06 | Bowler–batter matchups | **NEED** | No matrix build / insight type |
| F07 | Momentum Index (−1..+1 + percentiles) | **PARTIAL** | Momentum *situation* exists; no continuous index / slider / Cricsheet percentile baselines |
| F08 | AI narration + hard contract | **NEED** | Insights are template/pointer structured; no LLM layer |
| F09 | Weather-aware projections | **PARTIAL** | Weather/dew exist; no DLS lib; no WP/projection adjustment |
| F10 | Tactical Decision Assistant | **NEED** | — |
| F11 | Multi-format adaptive engine | **PARTIAL** | T20/IPL/IT20/ODI/ODM only; no Test / Hundred / T10 phase models |
| F12 | Historical What-If simulator | **PARTIAL** | `replay_engine.replay_to` exists; no user sim / Monte Carlo fork UI |
| F13 | Fantasy API | **NEED** | External scoring + squad data |
| F14 | Youth / domestic expansion | **NEED** | Corpus is Cricsheet majors |
| F15 | Integrity monitor | **NEED** | Blocked on legal review |

---

## 3. Revised critical path (ignore PDF week numbers)

Ship in dependency order. Prefer smallest vertical slices that hit Match Room + Tactical Read.

### Slice A — Integrity & trust (do first)
**F01 → F02 → F03 + doc sync**

1. **F01** Extract `PHASE_BOUNDARIES` to `intelligence/parser/constants.py`; import from the three consumers; one assert-based check that all readers share values.
2. **F02** Move `venue_data_is_reliable`, `player_data_is_reliable`, `DATA_CONFIDENCE_CUTOFF`, `SIGNIFICANCE_THRESHOLD_PCT` into `validation_engine.py`; keep Kallis refusal as a runnable check.
3. **F03** Write `generated_at` / `corpus_through` into venue + player context builds; expose on match-details payload; subtle freshness chip on Match Room + Tactical Read; stale if >14 days.
4. Update `ARCHITECTURE.md` Known Gaps to match code (collapse/partnership HAVE; chase HAVE; weather PARTIAL).

**Exit check:** phase values identical across modules; Kallis still refused; UI shows corpus date.

### Slice B — Insight depth (highest product leverage)
**F04 → F06 → F07 completion**

1. **F04** Enrich `player_stats.json`: last-10 / last-2y / last-5 form windows; per-venue batting/bowling; per-phase SR/economy by format. Guards: `MIN_VENUE_INNINGS=5`, `MIN_PHASE_BALLS=100`. New insight types: `player_phase_mismatch`, `venue_form_convergence`.
2. **F06** Build sparse `matchup_stats.json`; `MIN_MATCHUP_BALLS=30`; insight `bowler_batter_matchup`; Match Room card when both players are live.
3. **F07** Promote situation momentum into a continuous −1..+1 index with Cricsheet phase/format percentile baselines; optional slider on Match Room (keep existing discrete situation insights).

**Exit check:** one live match produces form/venue/phase and (when sample allows) matchup pointers; silent when guards fail.

### Slice C — Live decision layer
**F05 → F09 → thin F08**

1. **F05** Monte Carlo WP using venue phase run + wicket distributions; sit **beside** Chase Engine recovery/pace (do not replace). Early-innings uncertainty label. Backtest offline on completed chases before UI.
2. **F09** Dew/humidity/rain adjustments into WP + chase projections; DLS via established library only; weather already in UI — extend badge copy when model adjusts.
3. **F08** Narration only after B+C facts are rich: LLM receives structured insights only; number-extract validator; ≤3 retries; template fallback. Never skip validator.

**Exit check:** WP bar + chase signal both visible; dew HIGH can move WP; any narrated number matches insight object.

### Slice D — Expansion (after core is sticky)
**F11 → F12 → F10**

1. **F11** Format auto-detect; Test / Hundred phase defs in `constants.py`; T10 flagged experimental; format-specific significance thresholds.
2. **F12** What-If on top of `replay_engine` + F05; only XI players; actual vs simulated comparison; disclaimer.
3. **F10** Historical decision-outcome patterns (“promote hitter at RRR>X”); medium confidence + disclaimer; Tactical Board tab — after F04/F06 so recommendations cite real samples.

### Slice E — Monetize last (gated)
**F13 → F14 → F15**

- **F13** only with scoring-rule adapters + explicit “verify playing XI” flag; legal review for India fantasy markets.
- **F14** CSV upload + developmental-data flag; lower thresholds only when marked developmental.
- **F15** anomaly z-scores only after legal counsel; never “corruption” language.

---

## 4. What not to build yet (YAGNI)

- Replacing Chase Engine with Monte Carlo
- Field placement / shot type / ball speed features (Cricsheet cannot support)
- Custom DLS from scratch
- Integrity product UI before legal sign-off
- Narration layer before F04/F06 enrich the insight objects
- Parent/coach dashboard before CSV ingestion works

---

## 5. Suggested first PR sequence (code, not calendar)

| PR | Scope | Touches |
|---|---|---|
| 1 | F01 constants + ARCHITECTURE gap sync | `constants.py`, 3 importers, `ARCHITECTURE.md` |
| 2 | F02 validation extraction + Kallis check | `validation_engine.py`, `insight_engine.py` |
| 3 | F03 freshness in build + API + Match Room / Tactical chip | context builders, `app.py`, `MatchRoom.jsx`, `TacticalSheetLive.jsx` |
| 4 | F04 player enrichment + 2 insight types | `player_context.py`, context JSON, `insight_engine.py` |
| 5 | F06 matchup matrix + live card | new build module, Match Room |
| 6 | F05 WP engine + bar next to Chase | new module, venue dist fields, Match Room |
| 7 | F09 weather into WP/projections | `weather_service.py`, WP module |
| 8 | F08 narration hard contract | `narration_engine.py`, optional article path |

Each PR: one runnable check that fails if the new logic breaks (assert/`unittest`, no framework sprawl).

---

## 6. Success metrics (keep from PDF, tightened)

| Slice | Metric |
|---|---|
| A | Single source of phase bounds; freshness visible; Kallis still blocked |
| B | >0 form/venue/phase insights on qualified live players; matchup only when ≥30 balls |
| C | WP backtest within ±5% on held-out completed limited-overs chases; narrated numbers 100% validated |
| D | Format mis-label rate near zero on known Cricsheet types; What-If only allows XI players |
| E | Fantasy partners / integrity only after legal gate |

---

## 7. Bottom line

**Already have:** engine pipeline, guards-in-place, Chase Engine, situation detection, projections, weather/dew UI, Match Room, Tactical Read.

**Must add next:** consolidate constants + validation (trust), then player form/venue/phase + matchups (depth), then win probability beside chase (decision), then weather-adjusted models + hard-contract narration.

**Defer:** fantasy, youth ingest, integrity — after the Match Room is indispensable.

The moat is not Cricsheet. It is validated comparative intelligence on top of it. Protect that: silence when uncertain, never invent numbers, narrate only pre-verified facts.
