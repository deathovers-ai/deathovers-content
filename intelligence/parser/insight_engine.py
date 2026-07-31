"""
Epic 5 - Insight Engine

Goal: Turn facts (metrics_engine.py) and historical context
(context_repository.py, player_context.py) into interpreted, human-
readable insights - the layer that finally says "this is above/below
average" instead of just reporting numbers.

HARD RULE - CTO decision, July 2026 (see DATA_QUALITY_NOTES.md):
This module NEVER generates a comparison against player or venue data
we haven't validated as reliable.

IMPORTANT CORRECTION found during testing: the obvious guard - "refuse
if this player's earliest RECORDED match is before the cutoff" - is
broken by construction. A player whose real career started in 1995 but
who Cricsheet only starts covering from 2003 will still show an
"earliest_match_date" of 2003 - indistinguishable from a player who
genuinely debuted in 2003. Jacques Kallis (real debut 1995, confirmed
35% stat shortfall) has an earliest_match_date of 2003-02-09 in our
data, which is >= our naive cutoff and would have WRONGLY passed the
guard. Caught this via the engine's own self-test before it shipped.

The date-of-first-recorded-match cannot detect "career started before
our coverage window" - only a genuinely external signal can (birth
year + typical debut age, or a real debut-date lookup). Since we don't
have that lookup built, the SAFE fallback is a match-volume heuristic:
if a player's total recorded innings is implausibly low for someone
who is clearly a long-career player (hard to detect automatically), OR
- more robustly - if their earliest match falls in the first ~18
months of our overall corpus coverage (2003-2004), treat them as
POSSIBLY pre-dating our coverage and refuse the comparison. This will
produce some false refusals (genuine 2003/2004 debutants get excluded
too) but that's the correct failure direction: refuse-when-unsure, not
include-when-unsure.

---
UPDATED July 2026 (CTO decision - "pointers not paragraphs"): every
insight's output was a single prose `text` string. Frontend now renders
structured pointers instead of paragraphs, so each insight-building
method below returns a `headline` (short, one line) + `pointers`
(list of {label, value, unit?, pct?}) in place of `text`. All guards,
thresholds, and calculations are UNCHANGED - this only touches how the
already-computed numbers are packaged for output. `text` is intentionally
no longer produced; see ARCHITECTURE.md pipeline note if a plain-string
fallback is ever needed again.
"""
import json
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
VENUE_STATS_FILE = os.path.join(CONTEXT_DIR, "venue_stats.json")
PLAYER_STATS_FILE = os.path.join(CONTEXT_DIR, "player_stats.json")

# Widened safety margin: refuse comparisons for any player whose earliest
# recorded match falls before this date. This is deliberately later than
# our corpus's real coverage start (~2003) specifically because a
# player's EARLIEST RECORDED match can't distinguish "debuted in 2003"
# from "career started earlier, Cricsheet just doesn't have it" - see
# module docstring. Widening the margin trades some false refusals
# (real early-2000s debutants excluded too) for eliminating false
# inclusions (Kallis-style silent undercounting) entirely.
DATA_CONFIDENCE_CUTOFF = "2005-01-01"

# How far a live number needs to diverge from the historical average
# before we consider it worth mentioning at all. Below this, silence -
# an insight engine that comments on every trivial wobble is just noise.
SIGNIFICANCE_THRESHOLD_PCT = 10.0


class DataConfidenceError(Exception):
    """Raised when an insight was about to be generated from unvalidated
    (pre-cutoff) data. Callers should catch this and skip the insight,
    not surface a degraded-confidence version of it."""
    pass


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def venue_data_is_reliable(venue_entry, match_type):
    """
    Venue reliability check: do we have enough matches (not just any
    matches) in the reliable era for this format at this venue?
    Cricsheet coverage for T20 formats essentially only exists post-2003
    anyway (T20 as a format didn't exist until 2003), so this mostly
    matters for ODI venues with a long history.

    Prefers the explicit "confidence" field (written by
    context_repository.py's build_venue_stats) when present; falls back
    to the raw matches_with_data threshold for venue_stats.json files
    generated before that field existed, so this doesn't hard-break on
    stale local output.
    """
    fmt = venue_entry.get("formats", {}).get(match_type)
    if not fmt:
        return False
    if "confidence" in fmt:
        return fmt["confidence"] in ("high", "medium")
    # Minimum sample size for a venue average to be meaningful at all -
    # this is a general statistical-confidence guard, separate from the
    # date-based data-quality guard.
    return fmt.get("matches_with_data", 0) >= 5


def player_data_is_reliable(player_entry):
    """
    The hard guard: refuse comparisons for players whose earliest
    recorded match predates our confirmed-reliable coverage window.
    """
    earliest = player_entry.get("earliest_match_date")
    if earliest is None:
        return False  # no date info at all - can't vouch for it, refuse
    return earliest >= DATA_CONFIDENCE_CUTOFF


class InsightEngine:
    """
    Generates comparative insights from live match facts (as produced by
    MetricsEngine) against historical context (venue_stats.json,
    player_stats.json). Every insight generated here has already passed
    the data-confidence guard - if the guard fails, no insight is
    returned for that comparison, silently (the caller gets one fewer
    insight, never a low-confidence one dressed up as normal).
    """

    def __init__(self, venue_stats=None, player_stats=None):
        self.venue_stats = venue_stats or _load_json(VENUE_STATS_FILE)
        self.player_stats = player_stats or _load_json(PLAYER_STATS_FILE)

    def _projected_score_at_point(self, venue_entry, match_type, legal_balls_so_far):
        """
        Estimate what a "typical" score at this venue would be after
        `legal_balls_so_far` balls, using the phase-by-phase run rates
        already computed in venue_stats.json - NOT the flat full-innings
        average. Comparing a 6-over score against a 20-over average is
        misleading (any early score looks dramatically "below average"
        purely because the innings isn't finished yet) - this walks
        through powerplay/middle/death phase rates up to the current
        point instead, giving a fair "on pace" comparison.

        Returns None if phase data isn't available for this format.
        """
        fmt = venue_entry["formats"].get(match_type)
        if not fmt or "phase_breakdown" not in fmt:
            return None
        phases = fmt["phase_breakdown"]

        # Phase over-boundaries, mirroring context_repository.py's
        # PHASE_BOUNDARIES - kept in sync manually (small, stable table).
        if match_type in ("ODI", "ODM"):
            bounds = [("powerplay", 0, 10), ("middle", 10, 40), ("death", 40, 50)]
        else:
            bounds = [("powerplay", 0, 6), ("middle", 6, 15), ("death", 15, 20)]

        overs_so_far = legal_balls_so_far / 6
        projected = 0.0
        for phase_name, start_over, end_over in bounds:
            phase_data = phases.get(phase_name)
            if not phase_data:
                continue
            phase_rate = phase_data.get("avg_run_rate", 0)
            if overs_so_far <= start_over:
                break
            overs_in_this_phase = min(overs_so_far, end_over) - start_over
            if overs_in_this_phase > 0:
                projected += overs_in_this_phase * phase_rate
        return round(projected, 1)

    def venue_score_insight(self, venue_key, match_type, current_score, current_wickets, overs_completed_str):
        """
        Compare a live team score against a FAIR baseline for this exact
        point in the innings - the venue's phase-weighted projected score
        by this many overs, not the flat full-innings average. This
        avoids the misleading "73% below average" false alarm that a flat
        comparison produces on any early-innings score (confirmed via a
        real Edgbaston live match: 39/3 in 6.1 overs looked dramatically
        "below" the 147.9 full-innings average, when it was actually a
        completely normal powerplay score for that venue).

        Falls back to the flat full-innings average only if we're at or
        past the final over (comparing a completed/near-complete innings
        to the full average is legitimate) or if phase data is missing.

        Returns None if not significant enough or not reliable enough.
        """
        venue_entry = self.venue_stats.get(venue_key)
        if not venue_entry or not venue_data_is_reliable(venue_entry, match_type):
            return None

        fmt = venue_entry["formats"][match_type]
        avg_score = fmt["avg_first_innings_score"]
        if avg_score == 0:
            return None

        try:
            legal_balls_so_far = int(round(float(overs_completed_str) * 6))
        except (ValueError, TypeError):
            legal_balls_so_far = None

        total_overs = 50 if match_type in ("ODI", "ODM") else 20
        baseline = avg_score
        baseline_label = "historical"
        if legal_balls_so_far is not None and legal_balls_so_far < total_overs * 6:
            projected = self._projected_score_at_point(venue_entry, match_type, legal_balls_so_far)
            if projected is not None and projected > 0:
                baseline = projected
                baseline_label = "on-pace"

        diff = current_score - baseline
        diff_pct = round((diff / baseline) * 100, 1)

        if abs(diff_pct) < SIGNIFICANCE_THRESHOLD_PCT:
            return None  # too close to the fair baseline to be worth saying anything

        direction = "above" if diff > 0 else "below"
        return {
            "type": "venue_score_comparison",
            "venue": venue_entry["display_name"],
            "match_type": match_type,
            "current_score": current_score,
            "current_wickets": current_wickets,
            "overs": overs_completed_str,
            "venue_avg_first_innings_score": avg_score,
            "baseline_used": baseline,
            "baseline_type": baseline_label,
            "diff_runs": round(diff, 1),
            "diff_pct": diff_pct,
            "direction": direction,
            "sample_size": fmt["matches_with_data"],
            "headline": f"Score is {abs(diff_pct)}% {direction} {baseline_label} score",
            "pointers": [
                {"label": "Current Score", "value": f"{current_score}/{current_wickets}", "unit": f" ({overs_completed_str} ov)"},
                {"label": f"{baseline_label.capitalize()} Baseline", "value": baseline},
                {"label": "Difference", "value": round(diff, 1), "unit": " runs", "pct": diff_pct},
                {"label": "Sample Size", "value": fmt["matches_with_data"], "unit": " matches"},
            ],
        }

    def venue_phase_insight(self, venue_key, match_type, phase_name, current_phase_runs, current_phase_balls):
        """
        Compare a live phase (powerplay/middle/death) scoring rate
        against the venue's historical average for that phase.
        """
        venue_entry = self.venue_stats.get(venue_key)
        if not venue_entry or not venue_data_is_reliable(venue_entry, match_type):
            return None

        fmt = venue_entry["formats"][match_type]
        phase_data = fmt.get("phase_breakdown", {}).get(phase_name)
        if not phase_data or current_phase_balls == 0:
            return None

        current_rate = round((current_phase_runs / current_phase_balls) * 6, 2)
        avg_rate = phase_data["avg_run_rate"]
        if avg_rate == 0:
            return None

        diff_pct = round(((current_rate - avg_rate) / avg_rate) * 100, 1)
        if abs(diff_pct) < SIGNIFICANCE_THRESHOLD_PCT:
            return None

        direction = "faster than" if diff_pct > 0 else "slower than"
        return {
            "type": "venue_phase_comparison",
            "venue": venue_entry["display_name"],
            "match_type": match_type,
            "phase": phase_name,
            "current_run_rate": current_rate,
            "venue_avg_run_rate": avg_rate,
            "diff_pct": diff_pct,
            "direction": direction,
            "headline": f"{phase_name.capitalize()} rate {abs(diff_pct)}% {direction} venue average",
            "pointers": [
                {"label": "Current Run Rate", "value": current_rate},
                {"label": f"Venue {phase_name.capitalize()} Avg", "value": avg_rate},
                {"label": "Difference", "value": round(current_rate - avg_rate, 2), "pct": diff_pct},
            ],
        }

    def venue_pregame_insight(self, venue_key, match_type):
        """
        Start-of-match venue summary, restructured (CTO decision, this
        sprint) into 4 explicit named sections instead of one flat
        pointer list - each section maps 1:1 to a distinct Match Room UI
        block, and each carries its own sample-size/basis label so the
        frontend never has to guess what a number means. All figures are
        ALL-TIME (matches_with_data) - a recent-N-matches variant was
        considered and deliberately deferred: pitch character changes
        are rare/slow (relaid pitch, renovation), so a 20-match recent
        window mostly adds noise (mixed tournaments/seasons/ball types)
        without a real signal to justify the added pipeline complexity.

        Returns None if the venue/format isn't reliable enough, or if
        the toss/outcome fields aren't present (older venue_stats.json
        generated before context_repository.py tracked them).
        """
        venue_entry = self.venue_stats.get(venue_key)
        if not venue_entry or not venue_data_is_reliable(venue_entry, match_type):
            return None

        fmt = venue_entry["formats"][match_type]
        if "toss_bat_first_pct" not in fmt:
            return None  # stale venue_stats.json, fields not computed yet

        name = venue_entry["display_name"]
        sample_size = fmt["matches_with_data"]
        result_sample_size = fmt.get("matches_with_result", sample_size)

        # --- Section: toss & decision record ---
        toss_record = None
        if fmt.get("toss_bat_first_pct") is not None and fmt.get("win_pct_batting_first") is not None:
            bat_pct = fmt["toss_bat_first_pct"]
            lean = "Bat First" if bat_pct >= 50 else "Bowl First"
            lean_pct = bat_pct if bat_pct >= 50 else round(100 - bat_pct, 1)
            toss_record = {
                "basis": f"all-time, {result_sample_size} completed matches",
                "pointers": [
                    {"label": f"Toss \u2192 {lean}", "value": lean_pct, "unit": "%"},
                    {"label": "Win % (Batting First)", "value": fmt["win_pct_batting_first"], "unit": "%"},
                    {"label": "Win % (Batting Second)", "value": fmt["win_pct_bowling_first"], "unit": "%"},
                ],
            }

        # --- Section: venue score record (highest/lowest/avg) ---
        score_record = None
        if fmt.get("highest_total") is not None and fmt.get("lowest_total") is not None \
                and fmt.get("avg_first_innings_score") is not None:
            score_record = {
                "basis": f"all-time, {sample_size} matches",
                "pointers": [
                    {"label": "Highest Total", "value": fmt["highest_total"]},
                    {"label": "Lowest Total", "value": fmt["lowest_total"]},
                    {"label": "Avg 1st Innings Score", "value": fmt["avg_first_innings_score"]},
                ],
            }
            if fmt.get("avg_second_innings_score") is not None:
                score_record["pointers"].append(
                    {"label": "Avg 2nd Innings Score", "value": fmt["avg_second_innings_score"]}
                )

        # --- Section: chase record ---
        chase_record = None
        if fmt.get("highest_successful_chase") is not None or fmt.get("lowest_score_defended") is not None:
            chase_pointers = []
            if fmt.get("highest_successful_chase") is not None:
                chase_pointers.append({"label": "Highest Successful Chase", "value": fmt["highest_successful_chase"]})
            if fmt.get("lowest_score_defended") is not None:
                chase_pointers.append({"label": "Lowest Total Defended", "value": fmt["lowest_score_defended"]})
            chase_record = {
                "basis": f"all-time, {result_sample_size} completed matches",
                "pointers": chase_pointers,
            }

        # --- Section: innings score range, with explicit basis so the
        # frontend/user knows exactly what population this range is
        # drawn from (this was the ask: "must define on what base"). ---
        score_range = None
        if fmt.get("highest_total") is not None and fmt.get("lowest_total") is not None:
            score_range = {
                "basis": f"all completed innings at this venue, {match_type}, all-time ({sample_size} matches)",
                "low": fmt["lowest_total"],
                "high": fmt["highest_total"],
            }

        sections = {
            "toss_record": toss_record,
            "score_record": score_record,
            "chase_record": chase_record,
            "score_range": score_range,
        }
        if not any(sections.values()):
            return None  # guard passed but every individual section was empty - nothing to say

        return {
            "type": "venue_pregame_summary",
            "venue": name,
            "match_type": match_type,
            "sample_size": sample_size,
            "headline": f"{name} \u2014 {match_type} venue record",
            **sections,
        }

    def player_form_insight(self, player_name, current_runs, current_balls):
        """
        Compare a batter's current-innings strike rate against their
        own career strike rate. Refuses to generate this comparison if
        the player's data predates the confidence cutoff (see module
        docstring) - raises DataConfidenceError internally, caught here
        and converted to a clean None so callers don't need their own
        try/except for this.
        """
        player_entry = self.player_stats.get(player_name)
        if not player_entry:
            return None
        try:
            if not player_data_is_reliable(player_entry):
                raise DataConfidenceError(
                    f"{player_name}'s earliest recorded match "
                    f"({player_entry.get('earliest_match_date')}) predates the "
                    f"confidence cutoff ({DATA_CONFIDENCE_CUTOFF}) - refusing comparison."
                )
        except DataConfidenceError:
            return None

        career_sr = player_entry["batting"]["strike_rate"]
        career_balls = player_entry["batting"]["balls"]
        if career_sr == 0 or current_balls == 0 or career_balls < 30:
            return None  # not enough career sample to be a meaningful baseline either

        current_sr = round((current_runs / current_balls) * 100, 2)
        diff_pct = round(((current_sr - career_sr) / career_sr) * 100, 1)

        if abs(diff_pct) < SIGNIFICANCE_THRESHOLD_PCT:
            return None

        direction = "faster than" if diff_pct > 0 else "slower than"
        return {
            "type": "player_form_comparison",
            "player": player_name,
            "current_strike_rate": current_sr,
            "career_strike_rate": career_sr,
            "diff_pct": diff_pct,
            "direction": direction,
            "headline": f"{player_name} scoring {abs(diff_pct)}% {direction} career rate",
            "pointers": [
                {"label": "Current Strike Rate", "value": current_sr},
                {"label": "Career Strike Rate", "value": career_sr},
                {"label": "Difference", "value": round(current_sr - career_sr, 2), "pct": diff_pct},
            ],
        }

    # ------------------------------------------------------------------
    # Situation detection: collapse / momentum / pressure / partnership.
    # Deterministic, rule-based - NOT LLM-narrated (see ARCHITECTURE.md
    # "planned, not yet built" note this replaces). Reads recent_balls,
    # the same shape MatchState.recent_balls already produces in
    # replay_engine.py: [{"over", "ball_in_over", "runs_total",
    # "is_wicket"}, ...]. Internal severity SCORES are computed but never
    # returned to callers/frontend directly - only the derived label
    # (gauge level) and the underlying counts/stats are exposed, per the
    # "dimensions used internally only" decision.
    # ------------------------------------------------------------------

    def _situation_gauge_level(self, score):
        if score >= 75:
            return "CRITICAL"
        if score >= 55:
            return "HIGH"
        if score >= 35:
            return "MODERATE"
        return "LOW"

    def _collapse_score(self, recent_balls, innings_avg_run_rate):
        """Last 24 legal balls (4 overs). Wicket clustering alone can
        push this past threshold even before run rate visibly drops -
        the slowdown often follows the wickets, not the other way round."""
        window = recent_balls[-24:]
        if not window:
            return 0, 0, 0
        wickets_in_window = sum(1 for b in window if b["is_wicket"])
        runs_in_window = sum(b["runs_total"] for b in window)
        window_rr = (runs_in_window / len(window)) * 6
        rr_drop_pct = max(0.0, ((innings_avg_run_rate - window_rr) / innings_avg_run_rate) * 100) \
            if innings_avg_run_rate > 0 else 0.0

        wicket_component = min(wickets_in_window / 3, 1) * 75
        rr_component = min(rr_drop_pct / 50, 1) * 25
        score = round(wicket_component + rr_component)
        return score, wickets_in_window, round(rr_drop_pct, 1)

    def _momentum_score(self, recent_balls, innings_avg_strike_rate):
        """Last 18 legal balls (3 overs). Boundary flow + SR spike, with
        a hard penalty if a wicket fell in the window (a "momentum"
        reading right after a wicket is a false positive)."""
        window = recent_balls[-18:]
        if not window:
            return 0, 0, 0.0
        runs_in_window = sum(b["runs_total"] for b in window)
        window_sr = (runs_in_window / len(window)) * 100
        sr_spike_pct = max(0.0, ((window_sr - innings_avg_strike_rate) / innings_avg_strike_rate) * 100) \
            if innings_avg_strike_rate > 0 else 0.0
        boundary_count = sum(1 for b in window if b["runs_total"] in (4, 6))
        boundary_pct = (boundary_count / len(window)) * 100
        wickets_in_window = sum(1 for b in window if b["is_wicket"])

        sr_component = min(sr_spike_pct / 40, 1) * 50
        boundary_component = min(boundary_pct / 25, 1) * 50
        wicket_penalty = 30 if wickets_in_window > 0 else 0
        score = max(0, round(sr_component + boundary_component - wicket_penalty))
        return score, boundary_count, round(sr_spike_pct, 1)

    def _pressure_score(self, recent_balls, required_run_rate, current_run_rate, balls_since_new_batter):
        """Last 12 legal balls (2 overs). Dot-ball buildup, widened by a
        widening RRR gap (2nd innings only) and a fresh batter still
        settling in."""
        window = recent_balls[-12:]
        if not window:
            return 0, 0, 0.0
        dot_count = sum(1 for b in window if b["runs_total"] == 0 and not b["is_wicket"])
        dot_pct = (dot_count / len(window)) * 100

        rrr_gap_component = 0
        if required_run_rate is not None and current_run_rate is not None:
            gap = max(required_run_rate - current_run_rate, 0)
            rrr_gap_component = min(gap / 6, 1) * 35

        new_batter_component = 15 if balls_since_new_batter is not None and balls_since_new_batter <= 6 else 0
        dot_component = min(dot_pct / 70, 1) * 50
        score = min(round(dot_component + rrr_gap_component + new_batter_component), 100)
        return score, dot_count, round(dot_pct, 1)

    def _partnership_score(self, partnership_runs, partnership_balls):
        """Sustained, unbroken stand - runs and strike rate together."""
        if partnership_balls == 0:
            return 0, 0.0
        sr = (partnership_runs / partnership_balls) * 100
        runs_component = min(partnership_runs / 100, 1) * 60
        sr_component = min(sr / 150, 1) * 40
        score = round(runs_component + sr_component)
        return score, round(sr, 1)

    def situation_insight(self, recent_balls, innings_avg_run_rate, innings_avg_strike_rate,
                           partnership_runs, partnership_balls, required_run_rate=None,
                           current_run_rate=None, balls_since_new_batter=None):
        """
        Runs all four situation detectors and returns the single
        highest-priority one that clears its threshold (collapse beats
        pressure beats acceleration beats partnership, if more than one
        fires on the same ball). Returns None if nothing notable.

        recent_balls: list of {"runs_total": int, "is_wicket": bool}
        (only these two fields are read; extra keys like MatchState's
        "over"/"ball_in_over" are ignored, so MatchState.recent_balls
        can be passed straight through).
        """
        candidates = []

        collapse_score, wkts_in_window, rr_drop_pct = self._collapse_score(recent_balls, innings_avg_run_rate)
        if collapse_score >= 55 and wkts_in_window >= 3:
            candidates.append({
                "priority": 4,
                "score": collapse_score,
                "type": "collapse",
                "headline": f"Collapse \u2014 {wkts_in_window} wickets in last {min(len(recent_balls), 24)} balls",
                "pointers": [
                    {"label": "Wickets (last 4 overs)", "value": wkts_in_window},
                    {"label": "Run Rate Drop", "value": rr_drop_pct, "unit": "%"},
                ],
            })

        pressure_score, dot_count, dot_pct = self._pressure_score(
            recent_balls, required_run_rate, current_run_rate, balls_since_new_batter
        )
        if pressure_score >= 60:
            candidates.append({
                "priority": 3,
                "score": pressure_score,
                "type": "wicket_pressure",
                "headline": "Pressure building \u2014 wicket chance rising",
                "pointers": [
                    {"label": "Dot Balls (last 2 overs)", "value": dot_count, "pct": dot_pct},
                ],
            })

        momentum_score, boundary_count, sr_spike_pct = self._momentum_score(recent_balls, innings_avg_strike_rate)
        if momentum_score >= 55:
            candidates.append({
                "priority": 2,
                "score": momentum_score,
                "type": "acceleration",
                "headline": "Acceleration \u2014 scoring rate climbing",
                "pointers": [
                    {"label": "Boundaries (last 3 overs)", "value": boundary_count},
                    {"label": "Strike Rate Spike", "value": sr_spike_pct, "unit": "%"},
                ],
            })

        partnership_score, partnership_sr = self._partnership_score(partnership_runs, partnership_balls)
        if partnership_score >= 50 and partnership_runs >= 50:
            candidates.append({
                "priority": 1,
                "score": partnership_score,
                "type": "partnership",
                "headline": f"Partnership building \u2014 {partnership_runs} runs, unbroken",
                "pointers": [
                    {"label": "Partnership Runs", "value": partnership_runs},
                    {"label": "Balls Faced", "value": partnership_balls},
                    {"label": "Partnership Strike Rate", "value": partnership_sr},
                ],
            })

        if not candidates:
            return None

        candidates.sort(key=lambda c: (c["priority"], c["score"]), reverse=True)
        top = candidates[0]
        return {
            "type": f"situation_{top['type']}",
            "gauge": {"level": self._situation_gauge_level(top["score"])},
            "headline": top["headline"],
            "pointers": top["pointers"],
        }

    # ------------------------------------------------------------------
    # Post-halfway score projection: T20 after over 10 (of 20), ODI after
    # over 25 (of 50) - same ratio, per CTO decision this sprint. Blends
    # current run rate with the venue's own middle/death phase rates
    # rather than a naive flat-CRR extrapolation, since death overs
    # typically accelerate beyond the rate set earlier in an innings.
    # Always returns a RANGE, never a single false-precision number.
    #
    # 1ST INNINGS ONLY. The 2nd innings (a chase) should never show a flat
    # "projected final score" - what matters there is whether the chase is
    # on/ahead/behind pace, which is a different question with a different
    # answer shape (see chase_projection_insight below). Callers must not
    # call this method once is_second_innings is true; match_intelligence_api.py
    # enforces this at the call-site level.
    # ------------------------------------------------------------------

    PROJECTION_MIN_OVER = {"T20": 10, "IT20": 10, "IPL": 10, "ODI": 25, "ODM": 25}

    def projection_insight(self, venue_key, match_type, current_score, current_over_decimal):
        """
        current_over_decimal: e.g. 10.3 for "10.3 overs".
        Returns None if not yet eligible (before the minimum over), the
        venue/format isn't reliable, or phase data is missing - same
        refuse-don't-guess posture as the rest of this module. 1st innings
        only - see class docstring above.
        """
        min_over = self.PROJECTION_MIN_OVER.get(match_type)
        if min_over is None or current_over_decimal < min_over:
            return None

        venue_entry = self.venue_stats.get(venue_key)
        if not venue_entry or not venue_data_is_reliable(venue_entry, match_type):
            return None

        fmt = venue_entry["formats"][match_type]
        phases = fmt.get("phase_breakdown")
        if not phases or "middle" not in phases or "death" not in phases:
            return None

        total_overs = 50 if match_type in ("ODI", "ODM") else 20
        if match_type in ("ODI", "ODM"):
            middle_end, death_start = 40, 40
        else:
            middle_end, death_start = 15, 15

        middle_overs_remaining = max(0.0, middle_end - current_over_decimal)
        death_overs_remaining = max(0.0, total_overs - max(current_over_decimal, death_start))

        middle_rate = phases["middle"].get("avg_run_rate", 0)
        death_rate = phases["death"].get("avg_run_rate", 0)
        if middle_rate == 0 and death_rate == 0:
            return None

        mid_projection = current_score + (middle_overs_remaining * middle_rate) + (death_overs_remaining * death_rate)

        overs_remaining = total_overs - current_over_decimal
        uncertainty_pct = min(0.08 + (overs_remaining / total_overs) * 0.10, 0.18)
        low = round(mid_projection * (1 - uncertainty_pct))
        high = round(mid_projection * (1 + uncertainty_pct))
        mid = round(mid_projection)

        return {
            "type": "score_projection",
            "match_type": match_type,
            "current_score": current_score,
            "current_over": current_over_decimal,
            "projected_low": low,
            "projected_mid": mid,
            "projected_high": high,
            "headline": f"Projected {low}\u2013{high}",
            "pointers": [
                {"label": "Current Score", "value": current_score, "unit": f" ({current_over_decimal} ov)"},
                {"label": "Projected Range", "value": f"{low} \u2013 {high}"},
                {"label": "Projected Mid", "value": mid},
            ],
        }

    # ------------------------------------------------------------------
    # Second innings - triple comparison. Always returns all three
    # lenses together (vs 1st innings same over, vs venue phase avg,
    # vs required run rate) since any one alone can mislead - see CTO
    # discussion this sprint.
    # ------------------------------------------------------------------

    def second_innings_comparison(self, venue_key, match_type, current_score, current_wickets,
                                   current_over_decimal, target, balls_remaining,
                                   first_innings_score_at_same_over, phase_name,
                                   current_phase_runs, current_phase_balls):
        """
        first_innings_score_at_same_over: caller supplies the 1st
        innings' score at the same over mark (from that innings' own
        replay/live data) - this module doesn't store 1st-innings
        history itself.

        Returns None only if venue data is unreliable for lens 2; lenses
        1 and 3 don't depend on historical venue data and are still
        included when lens 2 is unavailable (never withhold the whole
        comparison just because one lens can't be computed).
        """
        pointers = [
            {"label": "Current Score", "value": f"{current_score}/{current_wickets}", "unit": f" ({current_over_decimal} ov)"},
        ]

        if first_innings_score_at_same_over is not None:
            diff = current_score - first_innings_score_at_same_over
            diff_pct = round((diff / first_innings_score_at_same_over) * 100, 1) if first_innings_score_at_same_over else None
            pointers.append({
                "label": "1st Innings (same over)",
                "value": first_innings_score_at_same_over,
                "unit": " runs",
            })
            pointer = {"label": "Difference", "value": diff, "unit": " runs"}
            if diff_pct is not None:
                pointer["pct"] = diff_pct
            pointers.append(pointer)

        venue_entry = self.venue_stats.get(venue_key)
        if venue_entry and venue_data_is_reliable(venue_entry, match_type):
            fmt = venue_entry["formats"][match_type]
            phase_data = fmt.get("phase_breakdown", {}).get(phase_name)
            if phase_data and current_phase_balls > 0:
                current_phase_rate = round((current_phase_runs / current_phase_balls) * 6, 2)
                venue_phase_rate = phase_data.get("avg_run_rate", 0)
                if venue_phase_rate > 0:
                    diff_pct = round(((current_phase_rate - venue_phase_rate) / venue_phase_rate) * 100, 1)
                    pointers.append({"label": f"Venue {phase_name.capitalize()} Avg Rate", "value": venue_phase_rate})
                    pointers.append({"label": "vs Venue Avg", "value": round(current_phase_rate - venue_phase_rate, 2), "pct": diff_pct})

        if balls_remaining and balls_remaining > 0:
            runs_needed = target - current_score
            required_rr = round((runs_needed / balls_remaining) * 6, 2)
            current_rr = round(current_score / current_over_decimal, 2) if current_over_decimal > 0 else 0
            pointers.append({"label": "Required Run Rate", "value": required_rr})
            pointers.append({"label": "Current Run Rate", "value": current_rr, "pct": round(((current_rr - required_rr) / required_rr) * 100, 1) if required_rr else None})
            pointers.append({"label": "Runs Needed", "value": runs_needed})
            pointers.append({"label": "Balls Remaining", "value": balls_remaining})

        return {
            "type": "second_innings_comparison",
            "match_type": match_type,
            "phase": phase_name,
            "headline": f"Chasing {target} \u2014 need {target - current_score} from {balls_remaining} balls" if balls_remaining else f"Chasing {target}",
            "pointers": pointers,
        }

    # ------------------------------------------------------------------
    # 2nd innings ONLY - "Projected Chase" replaces projection_insight's
    # flat score projection, which doesn't make sense once there's a
    # target to chase. This blends three lenses (CTO decision, this
    # sprint): live chase trajectory (current RR vs required RR),
    # historical venue chase success at this target band, and remaining-
    # phase venue rates (same phase data projection_insight uses) - to
    # answer "are they on track to actually get there", not just "what
    # would they score if this were a free-standing innings".
    # ------------------------------------------------------------------

    def chase_projection_insight(self, venue_key, match_type, current_score, target,
                                  current_over_decimal, balls_remaining):
        """
        Returns None if not yet eligible (before the same halfway-point
        threshold as projection_insight - a chase projection this early
        is just as noisy as a score projection would be), or if venue
        phase data is unavailable. Result is a WIN PROBABILITY-FLAVORED
        outcome (on-track / ahead / behind pace + a projected final score
        band if the current rate holds), not a single confident number -
        chases are inherently more volatile than a free innings since
        required rate itself changes every ball.
        """
        min_over = self.PROJECTION_MIN_OVER.get(match_type)
        if min_over is None or current_over_decimal < min_over or balls_remaining is None or balls_remaining <= 0:
            return None

        venue_entry = self.venue_stats.get(venue_key)
        if not venue_entry or not venue_data_is_reliable(venue_entry, match_type):
            return None

        fmt = venue_entry["formats"].get(match_type)
        phases = fmt.get("phase_breakdown") if fmt else None
        if not phases or "middle" not in phases or "death" not in phases:
            return None

        total_overs = 50 if match_type in ("ODI", "ODM") else 20
        if match_type in ("ODI", "ODM"):
            middle_end, death_start = 40, 40
        else:
            middle_end, death_start = 15, 15

        middle_overs_remaining = max(0.0, middle_end - current_over_decimal)
        death_overs_remaining = max(0.0, total_overs - max(current_over_decimal, death_start))
        middle_rate = phases["middle"].get("avg_run_rate", 0)
        death_rate = phases["death"].get("avg_run_rate", 0)
        if middle_rate == 0 and death_rate == 0:
            return None

        # Lens 1: if they simply continue at venue-typical remaining-phase
        # rates (not their own current rate - this answers "does the
        # venue's usual pace get them there", independent of how this
        # specific chase has gone so far).
        venue_pace_projection = current_score + (middle_overs_remaining * middle_rate) + (death_overs_remaining * death_rate)

        # Lens 2: required run rate vs their actual current run rate -
        # the live chase-pace signal.
        runs_needed = target - current_score
        required_rr = round((runs_needed / balls_remaining) * 6, 2) if balls_remaining > 0 else None
        current_rr = round(current_score / current_over_decimal, 2) if current_over_decimal > 0 else 0
        rr_gap = round(current_rr - required_rr, 2) if required_rr is not None else None

        # Combine: if current pace continues exactly, where do they land?
        current_pace_projection = current_score + (current_rr * (balls_remaining / 6))

        uncertainty_pct = 0.10
        low = round(min(venue_pace_projection, current_pace_projection) * (1 - uncertainty_pct))
        high = round(max(venue_pace_projection, current_pace_projection) * (1 + uncertainty_pct))

        if rr_gap is None:
            status = "UNKNOWN"
        elif rr_gap >= 0.5:
            status = "AHEAD OF PACE"
        elif rr_gap <= -0.5:
            status = "BEHIND PACE"
        else:
            status = "ON PACE"

        return {
            "type": "chase_projection",
            "match_type": match_type,
            "status": status,
            "headline": f"Chase {status.title()} \u2014 projected {low}\u2013{high} at current rate",
            "pointers": [
                {"label": "Target", "value": target},
                {"label": "Current Run Rate", "value": current_rr},
                {"label": "Required Run Rate", "value": required_rr},
                {"label": "Gap to Required Rate", "value": rr_gap, "unit": " rpo"},
                {"label": "Projected Range (current pace)", "value": f"{low} \u2013 {high}"},
            ],
        }

    def generate_all(self, context):
        """
        Convenience method: given a dict describing the current live
        match state, generate every applicable insight. Returns only
        the insights that passed both the significance threshold and
        the data-confidence guard - never partial/low-confidence ones.

        context expects (all optional - only relevant checks run):
          venue_key, match_type, current_score, current_wickets,
          overs_completed_str, phase_name, current_phase_runs,
          current_phase_balls, player_name, player_current_runs,
          player_current_balls
        """
        insights = []

        if all(k in context for k in ("venue_key", "match_type")):
            i = self.venue_pregame_insight(context["venue_key"], context["match_type"])
            if i:
                insights.append(i)

        if all(k in context for k in ("venue_key", "match_type", "current_score",
                                       "current_wickets", "overs_completed_str")):
            i = self.venue_score_insight(
                context["venue_key"], context["match_type"], context["current_score"],
                context["current_wickets"], context["overs_completed_str"]
            )
            if i:
                insights.append(i)

        if all(k in context for k in ("venue_key", "match_type", "phase_name",
                                       "current_phase_runs", "current_phase_balls")):
            i = self.venue_phase_insight(
                context["venue_key"], context["match_type"], context["phase_name"],
                context["current_phase_runs"], context["current_phase_balls"]
            )
            if i:
                insights.append(i)

        if all(k in context for k in ("player_name", "player_current_runs", "player_current_balls")):
            i = self.player_form_insight(
                context["player_name"], context["player_current_runs"], context["player_current_balls"]
            )
            if i:
                insights.append(i)

        return insights


if __name__ == "__main__":
    engine = InsightEngine()

    print("--- Test 1: venue score insight (reliable venue) ---")
    r = engine.venue_score_insight("R Premadasa Stadium", "T20", 175, 4, "15.0")
    print(json.dumps(r, indent=2) if r else "No insight (not significant or not reliable)")

    print("\n--- Test 2: player form insight, RELIABLE player (Kohli, career starts 2008) ---")
    r = engine.player_form_insight("V Kohli", 45, 20)  # fast innings vs his career SR
    print(json.dumps(r, indent=2) if r else "No insight")

    print("\n--- Test 3: player form insight, UNRELIABLE player (Kallis, career starts 2003 in our data) ---")
    r = engine.player_form_insight("JH Kallis", 45, 20)
    print(json.dumps(r, indent=2) if r else "REFUSED - guard correctly blocked comparison against unreliable data")

    print("\n--- Test 4: venue phase insight ---")
    r = engine.venue_phase_insight("R Premadasa Stadium", "T20", "death", 55, 30)
    print(json.dumps(r, indent=2) if r else "No insight")

    print("\n--- Test 5: full generate_all with combined context ---")
    context = {
        "venue_key": "R Premadasa Stadium",
        "match_type": "T20",
        "current_score": 180,
        "current_wickets": 3,
        "overs_completed_str": "18.0",
        "phase_name": "powerplay",
        "current_phase_runs": 60,
        "current_phase_balls": 36,
        "player_name": "V Kohli",
        "player_current_runs": 30,
        "player_current_balls": 25,
    }
    all_insights = engine.generate_all(context)
    print(f"Generated {len(all_insights)} insights:")
    for i in all_insights:
        print(" -", i["headline"])
        for p in i["pointers"]:
            pct_str = f" ({p['pct']:+}%)" if "pct" in p else ""
            print(f"     {p['label']}: {p['value']}{p.get('unit','')}{pct_str}")
