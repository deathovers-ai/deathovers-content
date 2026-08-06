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
| — | Weather + dew badge | **HAVE** | Fetched + shown; F09 wires dew/rain into WP + chase projection |
| F01 | Phase constants consolidation | **NEED** | Still 3 copies |
| F02 | `validation_engine.py` extraction | **NEED** | Guards still live inside `insight_engine.py` |
| F03 | Data freshness dashboard | **NEED** | No `generated_at` on context JSONs; no UI badge |
| F04 | Player form / venue / phase stats | **HAVE** | form / venues / phases + insights |
| F05 | Win probability (Monte Carlo) | **HAVE** | phase dists + MC beside Chase; early uncertainty label |
| F06 | Bowler–batter matchups | **HAVE** | `matchup_stats.json` + Match Room card |
| F07 | Momentum Index (−1..+1 + percentiles) | **HAVE** | continuous index + phase baselines + slider |
| F08 | AI narration + hard contract | **HAVE** | `narration_engine.py`; validated `narration` on insights; template / optional LLM |
| F09 | Weather-aware projections | **HAVE** | Dew HIGH/MOD moves WP + chase projection rates; rain → uncertainty only (no DLS) |
| F10 | Tactical Decision Assistant | **HAVE** | `decision_assistant.py` + `tactical_board` on match-details; Tactical Board tab; medium confidence + sample cites |
| F11 | Multi-format adaptive engine | **HAVE** | Ball-native Hundred; over-based T20/ODI; Test/FC explicitly unsupported (no T20 borrow); format-specific significance; T10 deferred; HND venue corpus still ops-blocked |
| F12 | Historical What-If simulator | **HAVE** | `what_if.py` + `/api/what-if` + Simulations tab; XI guard; actual vs fork WP; historical replay when events exist |
| F13 | Fantasy API | **NEED** | External scoring + squad data |
| F14 | Youth / domestic expansion | **NEED** | Corpus is Cricsheet majors |
| F15 | Integrity monitor | **NEED** | Blocked on legal review |

---

## 3. START NOW — detailed plan (do this first)

Do **not** start win probability, narration, fantasy, or What-If yet.  
Start with **Slice A** only. Three small PRs. No new dependencies. No UI redesign.

---

### Why start here

Phase boundaries are hardcoded in **four** places today (PDF said three — missed `app_integration.py`). If any one drifts, venue context and live phase insights silently disagree. Validation guards are buried inside the insight generator, so you cannot unit-test “should we speak?” separately from “what do we say?” Context JSONs have no freshness stamp, so users cannot tell if baselines are stale. Fix trust before adding smarter insights.

---

### PR 1 — F01: One source of phase boundaries

**Goal:** One dict. Four importers. Zero duplicated over ranges.

**Create** `intelligence/parser/constants.py`:

```python
PHASE_BOUNDARIES = {
    "T20_LIKE": {"powerplay": (0, 6), "middle": (6, 15), "death": (15, 20)},
    "ODI_LIKE": {"powerplay": (0, 10), "middle": (10, 40), "death": (40, 50)},
}

def phase_set_for_match_type(match_type: str) -> dict:
    """Return the phase window dict for a competition code."""
    return PHASE_BOUNDARIES["ODI_LIKE"] if match_type in ("ODI", "ODM") else PHASE_BOUNDARIES["T20_LIKE"]

def phase_bounds_list(match_type: str) -> list[tuple[str, int, int]]:
    """[(name, start_over, end_over), ...] in innings order."""
    phases = phase_set_for_match_type(match_type)
    return [(name, start, end) for name, (start, end) in phases.items()]
```

**Delete / replace duplicates in:**

| File | What to remove | Replace with |
|---|---|---|
| `context_repository.py` | local `PHASE_BOUNDARIES` dict (~L43–46); `phase_set_for_format` can keep signature but read from `constants` | `from constants import PHASE_BOUNDARIES` |
| `match_intelligence_api.py` | hardcoded `< 10 / < 40 / < 6 / < 15` in `determine_phase` | loop `phase_bounds_list(match_type)` |
| `insight_engine.py` | inline `bounds = [("powerplay",…)]` in `_projected_score_at_point` (~L154–157) | `phase_bounds_list(match_type)` |
| `app_integration.py` | inline `bounds = (...)` (~L148–151) | `phase_bounds_list(...)` |

**Also sync** `ARCHITECTURE.md` lines that say “duplicated across 3 files” → 4 files, then mark F01 done once merged.

**Runnable check** (`intelligence/parser/test_constants.py` or `__main__` on `constants.py`):

1. Assert T20 powerplay end == 6 and ODI death start == 40.
2. Import `determine_phase` and assert `determine_phase(5,"T20")=="powerplay"`, `determine_phase(6,"T20")=="middle"`, `determine_phase(39,"ODI")=="middle"`, `determine_phase(40,"ODI")=="death"`.
3. Assert `phase_bounds_list("IPL") == phase_bounds_list("T20")`.

**Do not:** add Test/Hundred/T10 phases here (that is F11). Only consolidate what already exists.

**Done when:** grep for `[(0, 6)` / `over_number < 6` phase tables finds no second copy; existing chase/insight tests still pass.

---

### PR 2 — F02: Extract validation engine

**Goal:** Insight generation imports guards; guards do not live inside insight methods.

**Create** `intelligence/parser/validation_engine.py` and move **unchanged**:

- `DATA_CONFIDENCE_CUTOFF = "2005-01-01"`
- `SIGNIFICANCE_THRESHOLD_PCT = 10.0`
- `DataConfidenceError`
- `venue_data_is_reliable(venue_entry, match_type)`
- `player_data_is_reliable(player_entry)`

**Update** `insight_engine.py`:

- Import those symbols from `validation_engine`.
- Leave all insight methods’ logic alone — this is a move, not a rewrite.

**Runnable check** (keep / relocate the existing Kallis self-test):

1. Load real `player_stats.json`.
2. Assert `player_data_is_reliable` is False for `JH Kallis` (or earliest date `< 2005-01-01`).
3. Assert True for a post-cutoff player that exists in the file (e.g. `V Kohli` if present).
4. Assert venue with `confidence: "low"` / `<5` matches fails `venue_data_is_reliable`.
5. Assert `SIGNIFICANCE_THRESHOLD_PCT == 10.0`.

**Do not:** change cutoff date, threshold %, or invent new guards. Extraction only.

**Done when:** `insight_engine.py` no longer defines the guard functions; Kallis still refused; venue/player insights still generate on happy-path fixtures.

---

### PR 3 — F03: Data freshness (build → API → UI)

**Goal:** Every context build stamps time; Match Room + Tactical Read show “Data current through …”; warn if >14 days old.

**Backend build**

1. In `build_venue_stats()` (`context_repository.py`) and `build_player_stats()` (`player_context.py`), wrap or annotate output with:

```json
{
  "_meta": {
    "generated_at": "ISO-8601 UTC",
    "corpus_through": "YYYY-MM-DD"
  },
  ...existing keys...
}
```

`corpus_through` = max match date seen while aggregating (already tracked per-player as `latest_match_date`; venues need the same max-date pass — add if missing).

2. Keep consumers tolerant: if `_meta` missing (old deploy), UI shows “Freshness unknown”, never crash.

**API** (`app.py` `_attach_intelligence` or match-details shaping):

- Read `_meta` from loaded venue/player stats (or from engine singleton).
- Attach to response, e.g. `shaped["intelligence"]["data_freshness"] = { generated_at, corpus_through, stale: bool }`.
- `stale = True` when `generated_at` older than 14 days.

**Frontend** (minimal, existing panels only):

| Surface | File | Change |
|---|---|---|
| Match Room | `MatchRoom.jsx` | Small chip in header: `DATA THRU {date}` / `REFRESH PENDING` if stale |
| Tactical Read | `TacticalSheetLive.jsx` | Same chip in `.tactical-header` / status area |

No new page. No dashboard redesign. One chip.

**Runnable check:**

1. Build path with a fake max date → `_meta.corpus_through` equals that date.
2. Unit/assert: age >14 days ⇒ `stale True`.
3. Manual: open Match Room / Tactical Read on a live match id; chip visible.

**Do not:** auto-refresh Cricsheet in this PR. Badge only. Corpus refresh remains a separate ops step.

**Done when:** committed context JSONs (or next rebuild) carry `_meta`; API exposes it; both UIs show it.

---

### PR 0 companion (same Slice A window) — fix stale docs

In `ARCHITECTURE.md` **KNOWN GAPS**:

| Current text | Correct to |
|---|---|
| Collapse/partnership “not built” | **Built** — situation detection in `insight_engine.py` + commentary derivation in `app.py` |
| Phase boundaries “3 files” | **4 files** until F01 lands; then “single `constants.py`” |
| Add missing HAVE | Chase Engine stack; weather/dew UI (not yet in projections) |

Also update the pipeline note that says Evidence/Validation aren’t separate — after F02, Validation **is** `validation_engine.py`.

---

### Slice A exit criteria (before starting Slice B)

- [ ] Grep shows one phase table only (`constants.py`)
- [ ] `validation_engine.py` owns all confidence guards
- [ ] Kallis regression check green in CI/local
- [ ] Freshness chip on Match Room + Tactical Read
- [ ] `ARCHITECTURE.md` matches reality
- [ ] No behavior change to Chase Engine, insights content, or live polling intervals

---

### Immediately after Slice A — Slice B start brief (do next, not now)

Only after the checklist above:

1. **F04 first half:** extend `player_context.py` with form windows (last 10 innings, last 2 years) — career block stays. Guards before any new insight type.
2. **F04 second half:** per-venue + per-phase player aggregates; insights `player_phase_mismatch`, `venue_form_convergence`.
3. **F06:** matchup matrix build + live Match Room card when sample ≥30 balls.

Do **not** open F05 (Monte Carlo) or F08 (LLM) until F04 is producing richer pointers in Tactical Read.

---

## 4. Full critical path (after start work)

Ship in dependency order. Prefer smallest vertical slices that hit Match Room + Tactical Read.

### Slice A — Integrity & trust (CURRENT FOCUS)
**F01 → F02 → F03 + doc sync** — detailed steps in §3 above.

**Exit check:** phase values identical across modules; Kallis still refused; UI shows corpus date.

### Slice B — Insight depth (highest product leverage)
**F04 → F06 → F07 completion**

1. **F04** Enrich `player_stats.json`: last-10 / last-2y / last-5 form windows; per-venue batting/bowling; per-phase SR/economy by format. Guards: `MIN_VENUE_INNINGS=5`, `MIN_PHASE_BALLS=100`. New insight types: `player_phase_mismatch`, `venue_form_convergence`.
2. **F06** Build sparse `matchup_stats.json`; `MIN_MATCHUP_BALLS=30`; insight `bowler_batter_matchup`; Match Room card when both players are live.
3. **F07** Promote situation momentum into a continuous −1..+1 index with Cricsheet phase/format percentile baselines; optional slider on Match Room (keep existing discrete situation insights).

**Exit check:** one live match produces form/venue/phase and (when sample allows) matchup pointers; silent when guards fail.

### Slice C — Live decision layer
**F05 → F09 → thin F08**

1. **F05** Monte Carlo WP using venue phase run + wicket distributions; sit **beside** Chase Engine recovery/pace (do not replace). Early-innings uncertainty label. Backtest offline on completed chases before UI. **DONE** (`win_probability.py`, Match Room WP orb + bar).
2. **F09** Dew/humidity/rain adjustments into WP + chase projections; DLS via established library only; weather already in UI — extend badge copy when model adjusts. **DONE** (`compute_weather_adjustment`; dew HIGH can move WP; rain marks uncertainty only — no custom DLS).
3. **F08** Narration — **DONE** (`narration_engine.py`): LLM optional; number-extract validator; ≤3 retries; template fallback. Never skip validator.

**Exit check:** WP bar + chase signal both visible; dew HIGH can move WP; any narrated number matches insight object.

### Slice D — Expansion (after core is sticky)
**F11 → F12 → F10**

1. **F11** Multi-format — **DONE** for code path: Hundred ball-native; Test/FC refuse limited-overs phases; format-specific significance thresholds; T10 deferred. HND venue corpus rebuild remains an ops/data step when events are available.
2. **F12** What-If — **DONE** (`what_if.py`, `/api/what-if`, Simulations tab): fork chase facts + F05 MC; XI ⊆11; disclaimer; historical actual when events present.
3. **F10** Tactical Decision Assistant — **DONE** (`decision_assistant.py`, `tactical_board` on match-details, Tactical Board tab): promote/consolidate/death/matchup patterns; medium confidence + disclaimer; cites cohort/matchup/phase samples.

### Slice E — Monetize last (gated)
**F13 → F14 → F15**

- **F13** only with scoring-rule adapters + explicit “verify playing XI” flag; legal review for India fantasy markets.
- **F14** CSV upload + developmental-data flag; lower thresholds only when marked developmental.
- **F15** anomaly z-scores only after legal counsel; never “corruption” language.

---

## 5. What not to build yet (YAGNI)

- Replacing Chase Engine with Monte Carlo
- Field placement / shot type / ball speed features (Cricsheet cannot support)
- Custom DLS from scratch
- Integrity product UI before legal sign-off
- Narration layer before F04/F06 enrich the insight objects
- Parent/coach dashboard before CSV ingestion works

---

## 6. Suggested first PR sequence (code, not calendar)

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

## 7. Success metrics (keep from PDF, tightened)

| Slice | Metric |
|---|---|
| A | Single source of phase bounds; freshness visible; Kallis still blocked |
| B | >0 form/venue/phase insights on qualified live players; matchup only when ≥30 balls |
| C | WP backtest within ±5% on held-out completed limited-overs chases; narrated numbers 100% validated |
| D | Format mis-label rate near zero on known Cricsheet types; What-If only allows XI players |
| E | Fantasy partners / integrity only after legal gate |

---

## 8. Bottom line

**Already have:** engine pipeline, guards-in-place, Chase Engine, situation detection, projections, weather/dew UI, Match Room, Tactical Read.

**Must add next:** consolidate constants + validation (trust), then player form/venue/phase + matchups (depth), then win probability beside chase (decision), then weather-adjusted models + hard-contract narration.

**Defer:** fantasy, youth ingest, integrity — after the Match Room is indispensable.

The moat is not Cricsheet. It is validated comparative intelligence on top of it. Protect that: silence when uncertain, never invent numbers, narrate only pre-verified facts.
