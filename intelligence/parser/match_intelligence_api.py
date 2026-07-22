"""
Epic 6 - Single Match Intelligence API

One clean function that takes live match state (in the shape
app_integration.py's build_live_state() produces) and returns Insight
Engine output - venue comparisons, phase comparisons, player form -
ready to send straight to the frontend's Insight tab.
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
        # resolve_venue_key tries the direct normalized name first, then
        # falls back to stripping a generic suffix word (e.g. "Lord's
        # Cricket Ground, London" -> "Lord's") to bridge the gap between
        # Cricbuzz's fuller venue naming and Cricsheet's terser one - see
        # its docstring in context_repository.py.
        venue_key = resolve_venue_key(live_state["venue_name"], engine.venue_stats)
        if venue_key is None:
            fallback_display = normalize_venue(live_state["venue_name"])
            warnings.append(f"Venue '{fallback_display}' (normalized from '{live_state['venue_name']}') "
                             f"not found in venue_stats.json - venue insights skipped.")

    context = {}

    if match_type and venue_key and venue_key in engine.venue_stats:
        # venue_key/match_type go in unconditionally here (not gated on a
        # live score existing) so venue_pregame_insight can fire before a
        # ball is bowled - the score-dependent insights below still only
        # populate their own extra fields once live_state actually has them.
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

    if live_state.get("striker_name") and "striker_current_runs" in live_state \
            and "striker_current_balls" in live_state:
        context.update({
            "player_name": live_state["striker_name"],
            "player_current_runs": live_state["striker_current_runs"],
            "player_current_balls": live_state["striker_current_balls"],
        })

    insights = engine.generate_all(context) if context else []

    return {
        "insights": insights,
        "meta": {
            "venue_key_used": venue_key,
            "format_used": match_type,
            "warnings": warnings,
        },
    }
