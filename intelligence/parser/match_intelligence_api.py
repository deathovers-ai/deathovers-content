"""
Epic 6 - Single Match Intelligence API

One clean function that takes live match state (in the shape
app_integration.py's build_live_state() produces) and returns Insight
Engine output - venue comparisons, phase comparisons, player form,
situation alerts, score projection, and (2nd innings) triple
comparison - ready to send straight to the frontend's Insight tab.

UPDATED July 2026: wires in the 3 new InsightEngine methods
(situation_insight, projection_insight, second_innings_comparison)
added this sprint. Each is gated on live_state actually containing the
fields it needs - same "only run what we have real data for" posture
as the original 4 insight types below. See app.py wiring notes at the
bottom of this file for what app.py itself still needs to track and
pass through (recent_balls history and 1st-innings archive aren't
buildable from a single miniscore snapshot - they require accumulation
across polls, which only app.py's persistent cache can do).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_repository import normalize_venue, resolve_venue_key
from insight_engine import InsightEngine

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = InsightEngine()
    return _engine


CRICBUZZ_FORMAT_MAP = {
    "T20": "T20",
    "T20I": "IT20",
    "ODI": "ODI",
    "TEST": None,
    "IPL": "IPL",
}


def map_format(cricbuzz_format_str, is_ipl=False):
    if is_ipl:
        return "IPL"
    return CRICBUZZ_FORMAT_MAP.get((cricbuzz_format_str or "").upper(), None)


def determine_phase(over_number, match_type):
    """Given the current over (0-indexed) and format, return which phase
    we're in. Mirrors the boundaries used in context_repository.py."""
    if match_type in ("ODI", "ODM"):
        if over_number < 10:
            return "powerplay"
        elif over_number < 40:
            return "middle"
        else:
            return "death"
    else:
        if over_number < 6:
            return "powerplay"
        elif over_number < 15:
            return "middle"
        else:
            return "death"


def get_match_insights(live_state):
    """
    Main entrypoint. live_state is a dict describing the current live
    match (see app_integration.py's build_live_state for how it's built).

    Returns:
    {
        "insights": [ {...}, {...} ],
        "meta": {
            "venue_key_used": ...,
            "format_used": ...,
            "warnings": [ ... ]
        }
    }
    """
    engine = get_engine()
    warnings = []

    match_type = map_format(live_state.get("match_format", ""), live_state.get("is_ipl", False))
    if match_type is None:
        warnings.append(
            f"Could not map Cricbuzz format '{live_state.get('match_format')}' "
            f"to an internal format - venue/phase insights skipped."
        )

    venue_key = None
    if live_state.get("venue_name"):
        venue_key = resolve_venue_key(live_state["venue_name"], engine.venue_stats)
        if venue_key is None:
            fallback_display = normalize_venue(live_state["venue_name"])
            warnings.append(f"Venue '{fallback_display}' (normalized from '{live_state['venue_name']}') "
                             f"not found in venue_stats.json - venue insights skipped.")

    context = {}

    if match_type and venue_key and venue_key in engine.venue_stats:
        context.update({"venue_key": venue_key, "match_type": match_type})

        if all(k in live_state for k in ("current_score", "current_wickets", "overs_completed_str")):
            context.update({
                "current_score": live_state["current_score"],
                "current_wickets": live_state["current_wickets"],
                "overs_completed_str": live_state["overs_completed_str"],
            })

        if "current_over_number" in live_state:
            phase = determine_phase(live_state["current_over_number"], match_type)
            context.update({"phase_name": phase})

            # NEW: run-rate comparison (venue_phase_insight, fed by this
            # phase_name key alongside current_phase_runs/balls below)
            # should surface as a checkpoint every 5 overs, not on every
            # single poll - CTO decision this sprint, same interval for
            # both T20 and ODI. current_phase_runs/current_phase_balls
            # are only meaningful for the CURRENT phase anyway (see
            # app_integration.py's phase-tracking notes), so this simply
            # withholds those two keys from context on off-checkpoint
            # overs, which correctly makes venue_phase_insight's own
            # guard in generate_all() skip it for that poll.
            is_five_over_checkpoint = live_state["current_over_number"] > 0 \
                and live_state["current_over_number"] % 5 == 0
            if not is_five_over_checkpoint:
                live_state = dict(live_state)  # avoid mutating caller's dict
                live_state.pop("current_phase_runs", None)
                live_state.pop("current_phase_balls", None)

    if live_state.get("striker_name") and "striker_current_runs" in live_state \
            and "striker_current_balls" in live_state:
        context.update({
            "player_name": live_state["striker_name"],
            "player_current_runs": live_state["striker_current_runs"],
            "player_current_balls": live_state["striker_current_balls"],
        })

    insights = engine.generate_all(context) if context else []

    # ------------------------------------------------------------------
    # NEW: situation_insight - needs recent_balls (ball-by-ball history,
    # NOT derivable from a single miniscore snapshot). Only runs if
    # app.py has actually populated live_state["recent_balls"] - see
    # wiring notes at bottom of this file. Silently skipped otherwise,
    # same refuse-don't-guess posture as everything else here.
    # ------------------------------------------------------------------
    if live_state.get("recent_balls") and "current_score" in live_state:
        legal_balls_so_far = live_state.get("legal_balls_bowled")
        innings_avg_rr = None
        innings_avg_sr = None
        if legal_balls_so_far:
            innings_avg_rr = round((live_state["current_score"] / legal_balls_so_far) * 6, 2)
            innings_avg_sr = round((live_state["current_score"] / legal_balls_so_far) * 100, 2)

        if innings_avg_rr is not None:
            situation = engine.situation_insight(
                recent_balls=live_state["recent_balls"],
                innings_avg_run_rate=innings_avg_rr,
                innings_avg_strike_rate=innings_avg_sr,
                partnership_runs=live_state.get("partnership_runs", 0),
                partnership_balls=live_state.get("partnership_balls", 0),
                required_run_rate=live_state.get("required_run_rate"),
                current_run_rate=innings_avg_rr,
                balls_since_new_batter=live_state.get("balls_since_new_batter"),
            )
            if situation:
                insights.append(situation)
        else:
            warnings.append("recent_balls present but legal_balls_bowled missing - situation_insight skipped.")

    # ------------------------------------------------------------------
    # UPDATED: projection_insight is 1ST INNINGS ONLY (a flat score
    # projection doesn't make sense once there's a target - see
    # chase_projection_insight below, which replaces it for the chase).
    # Needs venue_key/match_type (already resolved above) plus current
    # over as a decimal (e.g. 10.3). Threshold: T20 over 10, ODI over 25
    # (halfway point for both formats, CTO decision this sprint).
    # current_wickets is now REQUIRED (wickets-in-hand adjustment, CTO
    # decision this sprint) - a projection without it would be exactly
    # the wicket-blind gap this update exists to close, so it's withheld
    # entirely rather than silently falling back to a wicket-blind number.
    # ------------------------------------------------------------------
    is_second_innings = bool(live_state.get("is_second_innings"))
    if not is_second_innings and match_type and venue_key and "current_over_decimal" in live_state \
            and "current_score" in live_state and "current_wickets" in live_state:
        projection = engine.projection_insight(
            venue_key=venue_key,
            match_type=match_type,
            current_score=live_state["current_score"],
            current_over_decimal=live_state["current_over_decimal"],
            current_wickets=live_state["current_wickets"],
        )
        if projection:
            insights.append(projection)

    # ------------------------------------------------------------------
    # NEW: chase_projection_insight - 2ND INNINGS ONLY. Same halfway-point
    # threshold as projection_insight, but answers "are they on track to
    # reach the target" instead of "what would they score" - a different
    # question with a different, more volatile answer shape.
    # ------------------------------------------------------------------
    if is_second_innings and match_type and venue_key \
            and all(k in live_state for k in ("current_score", "target", "current_over_decimal", "balls_remaining")):
        chase_projection = engine.chase_projection_insight(
            venue_key=venue_key,
            match_type=match_type,
            current_score=live_state["current_score"],
            target=live_state["target"],
            current_over_decimal=live_state["current_over_decimal"],
            balls_remaining=live_state["balls_remaining"],
        )
        if chase_projection:
            insights.append(chase_projection)

    # ------------------------------------------------------------------
    # NEW: second_innings_comparison - needs target + 1st innings
    # archive (app.py must have stored innings-1's over-by-over score
    # somewhere retrievable - see wiring notes at bottom of this file).
    # Only runs when live_state explicitly marks this as the 2nd innings
    # via "is_second_innings" and supplies "target"/"balls_remaining".
    # ------------------------------------------------------------------
    if live_state.get("is_second_innings") and match_type and venue_key \
            and all(k in live_state for k in ("current_score", "current_wickets",
                                               "current_over_decimal", "target", "balls_remaining")):
        phase = determine_phase(live_state.get("current_over_number", 0), match_type)
        second_inn = engine.second_innings_comparison(
            venue_key=venue_key,
            match_type=match_type,
            current_score=live_state["current_score"],
            current_wickets=live_state["current_wickets"],
            current_over_decimal=live_state["current_over_decimal"],
            target=live_state["target"],
            balls_remaining=live_state["balls_remaining"],
            first_innings_score_at_same_over=live_state.get("first_innings_score_at_same_over"),
            phase_name=phase,
            current_phase_runs=live_state.get("current_phase_runs", 0),
            current_phase_balls=live_state.get("current_phase_balls", 0),
        )
        if second_inn:
            insights.append(second_inn)

    return {
        "insights": insights,
        "meta": {
            "venue_key_used": venue_key,
            "format_used": match_type,
            "warnings": warnings,
        },
    }


# ============================================================================
# APP.PY WIRING NOTES - what still needs to be added there for the 3 new
# insight types to actually fire on a live match. None of this is guessable
# from match_intelligence_api.py/app_integration.py alone; it requires
# app.py's own persistent per-match cache (the dict that already survives
# across polls for quota-tracking, per ARCHITECTURE.md's "three-tier
# interval scheduling" section).
# ============================================================================
#
# 1. recent_balls (for situation_insight):
#    app.py needs to accumulate a rolling ball-by-ball list per match_id
#    as new commentary/miniscore snapshots come in - Cricbuzz's /comm
#    endpoint gives discrete events, not a persistent list, so app.py's
#    existing per-match detail cache needs a new key, e.g.:
#      cache[match_id]["recent_balls"] = cache[match_id].get("recent_balls", [])
#    ...append each new legal delivery as {"runs_total": int, "is_wicket": bool}
#    when a new commentary line is detected (app.py already has ball-level
#    commentary parsing per ARCHITECTURE.md's pagination/backfill section -
#    this reuses that existing parse, doesn't need new Cricbuzz calls).
#    Cap the list length (e.g. last 30 balls) to bound cache memory.
#
# 2. legal_balls_bowled, partnership_runs, partnership_balls,
#    balls_since_new_batter:
#    legal_balls_bowled = current_over_number * 6 + ball_in_over (derivable
#    from miniscore's overs field, already available).
#    partnership_runs/balls and balls_since_new_batter require tracking the
#    striker/non-striker pair and detecting when it changes (a wicket or
#    retirement) - reset partnership counters to 0 when the pair changes,
#    increment every ball otherwise. This is new state app.py must track,
#    not derivable from a single snapshot.
#
# 3. current_over_decimal:
#    Trivial - this is just float(miniscore["inningsscores"]["inningsscore"]
#    [current]["overs"]), already available, just needs passing through
#    build_live_state() as a new key (it currently only derives
#    current_over_number as an int, losing the ball-within-over part).
#
# 4. is_second_innings, target, balls_remaining,
#    first_innings_score_at_same_over:
#    is_second_innings = miniscore["inningsid"] == 2 (already available).
#    target = miniscore["target"] (already available per app_integration.py's
#    REVISION 3 notes).
#    balls_remaining = (total_overs * 6) - legal_balls_bowled.
#    first_innings_score_at_same_over is the hardest piece: app.py must
#    have archived innings-1's own over-by-over score progression (e.g. a
#    list of {over, runs} snapshots taken each time innings-1 was polled)
#    somewhere keyed by match_id, so once innings-2 begins this can be
#    looked up. This does NOT exist yet anywhere in the current pipeline -
#    it requires app.py to start recording an over-by-over trail during
#    innings-1, not just the latest snapshot it currently keeps.
# ============================================================================
