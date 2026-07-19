"""
Epic 6 integration guide for app.py — REVISION 3 (final, verified)

Confirmed real field names from an actual RapidAPI response:
  miniscore.batsmanstriker = {"name": ..., "runs": ..., "balls": ..., ...}
  miniscore.batsmannonstriker = { same shape }
  miniscore.crr, miniscore.rrr, miniscore.target
  miniscore.inningsscores.inningsscore = [{"inningsid":, "runs":, "wickets":, "overs":, ...}]
  miniscore.inningsid = which innings is currently live
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_repository import normalize_venue
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
}


def map_format(cricbuzz_format_str, is_ipl=False):
    if is_ipl:
        return "IPL"
    return CRICBUZZ_FORMAT_MAP.get((cricbuzz_format_str or "").upper())


def build_live_state(venue_name, match_format_str, is_ipl, miniscore):
    """
    Builds the live_state dict get_match_insights() expects.
    """
    live_state = {
        "venue_name": venue_name or "",
        "match_format": match_format_str or "",
        "is_ipl": is_ipl,
    }

    if not miniscore:
        return live_state

    current_innings_id = miniscore.get("inningsid")
    innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])
    current_innings = next((s for s in innings_scores if s.get("inningsid") == current_innings_id), None)
    if current_innings is None and innings_scores:
        current_innings = max(innings_scores, key=lambda s: s.get("inningsid", 0))

    if current_innings:
        live_state["current_score"] = current_innings.get("runs")
        live_state["current_wickets"] = current_innings.get("wickets")
        overs_val = current_innings.get("overs")
        if overs_val is not None:
            live_state["overs_completed_str"] = str(overs_val)
            # Cricbuzz's "overs" is overs.balls notation (e.g. "15.4" means
            # 15 overs and 4 balls), NOT a decimal number of overs - so this
            # must be split on "." and only the whole-overs part parsed as
            # an int. int("15.4") raises ValueError, which was previously
            # uncaught here and silently killed every insight for any over
            # that wasn't exactly on a boundary (i.e. almost always).
            whole_overs_str = str(overs_val).split(".")[0]
            try:
                live_state["current_over_number"] = int(whole_overs_str)
            except (TypeError, ValueError):
                pass

    striker = miniscore.get("batsmanstriker")
    if striker and striker.get("name") and striker.get("runs") is not None and striker.get("balls") is not None:
        live_state["striker_name"] = striker["name"]
        live_state["striker_current_runs"] = striker["runs"]
        live_state["striker_current_balls"] = striker["balls"]

    return live_state


def get_insights_for_match(venue_name, match_format_str, is_ipl, miniscore):
    """
    Convenience one-call wrapper: build live_state and run the Insight
    Engine in one step.
    """
    from match_intelligence_api import get_match_insights
    live_state = build_live_state(venue_name, match_format_str, is_ipl, miniscore)
    return get_match_insights(live_state)
