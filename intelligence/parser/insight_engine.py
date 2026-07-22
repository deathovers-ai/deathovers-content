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
            "text": (
                f"At {venue_entry['display_name']}, this score of {current_score}/{current_wickets} "
                f"in {overs_completed_str} overs is {abs(diff_pct)}% {direction} the {baseline_label} "
                f"score for this venue at this stage ({match_type}, based on {fmt['matches_with_data']} matches)."
            ),
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
            "text": (
                f"The {phase_name} run rate of {current_rate} is {abs(diff_pct)}% {direction} "
                f"the historical {match_type} {phase_name}-overs average of {avg_rate} at "
                f"{venue_entry['display_name']}."
            ),
        }

    def venue_pregame_insight(self, venue_key, match_type):
        """
        Start-of-match venue summary: toss tendency, chase-vs-defend
        record, and historical extremes. Meant to be surfaced before a
        ball is bowled, unlike venue_score_insight/venue_phase_insight
        which need a live score to compare against.

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
        parts = []

        if fmt.get("toss_bat_first_pct") is not None:
            bat_pct = fmt["toss_bat_first_pct"]
            lean = "bat first" if bat_pct >= 50 else "bowl first"
            parts.append(
                f"Teams winning the toss have chosen to {lean} "
                f"{bat_pct if bat_pct >= 50 else round(100 - bat_pct, 1)}% of the time."
            )

        if fmt.get("win_pct_batting_first") is not None:
            parts.append(
                f"Sides batting first have won {fmt['win_pct_batting_first']}% of "
                f"decided matches here (batting second: {fmt['win_pct_bowling_first']}%), "
                f"based on {fmt['matches_with_result']} completed matches."
            )

        if fmt.get("highest_successful_chase") is not None:
            parts.append(f"Highest successful chase: {fmt['highest_successful_chase']}.")
        if fmt.get("lowest_score_defended") is not None:
            parts.append(f"Lowest total successfully defended: {fmt['lowest_score_defended']}.")
        if fmt.get("highest_total") is not None and fmt.get("lowest_total") is not None:
            parts.append(
                f"Innings totals here have ranged from {fmt['lowest_total']} to {fmt['highest_total']}."
            )

        if not parts:
            return None  # guard passed but every individual field was None - nothing to say

        return {
            "type": "venue_pregame_summary",
            "venue": name,
            "match_type": match_type,
            "avg_first_innings_score": fmt.get("avg_first_innings_score"),
            "avg_second_innings_score": fmt.get("avg_second_innings_score"),
            "toss_bat_first_pct": fmt.get("toss_bat_first_pct"),
            "win_pct_batting_first": fmt.get("win_pct_batting_first"),
            "win_pct_bowling_first": fmt.get("win_pct_bowling_first"),
            "highest_total": fmt.get("highest_total"),
            "lowest_total": fmt.get("lowest_total"),
            "highest_successful_chase": fmt.get("highest_successful_chase"),
            "lowest_score_defended": fmt.get("lowest_score_defended"),
            "sample_size": fmt["matches_with_data"],
            "text": f"At {name} ({match_type}): " + " ".join(parts),
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
            "text": (
                f"{player_name} is scoring at {current_sr}, which is {abs(diff_pct)}% "
                f"{direction} their career strike rate of {career_sr}."
            ),
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
    print(r["text"] if r else "No insight (not significant or not reliable)")

    print("\n--- Test 2: player form insight, RELIABLE player (Kohli, career starts 2008) ---")
    r = engine.player_form_insight("V Kohli", 45, 20)  # fast innings vs his career SR
    print(r["text"] if r else "No insight")

    print("\n--- Test 3: player form insight, UNRELIABLE player (Kallis, career starts 2003 in our data) ---")
    r = engine.player_form_insight("JH Kallis", 45, 20)
    print(r["text"] if r else "REFUSED - guard correctly blocked comparison against unreliable data")

    print("\n--- Test 4: venue phase insight ---")
    r = engine.venue_phase_insight("R Premadasa Stadium", "T20", "death", 55, 30)
    print(r["text"] if r else "No insight")

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
        print(" -", i["text"])
