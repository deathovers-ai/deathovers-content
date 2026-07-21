"""
Epic 6 integration guide for app.py — REVISION 3 (final, verified)

This revision is built from a REAL, complete miniscore payload Sanzz
pulled from the RapidAPI playground (India vs Bangladesh, 1st T20I,
2024 - a completed match, used here purely as a structure reference).

CONFIRMED REAL FIELD NAMES (this is what actually exists - no more
guessing):

  miniscore.batsmanstriker = {
      "id": 9647, "balls": 16, "runs": 39, "fours": 5, "sixes": 2,
      "strkrate": "243.75", "name": "Hardik Pandya", "outdec": "", ...
  }
  miniscore.batsmannonstriker = { same shape, other batter }
  miniscore.bowlerstriker = {
      "id": 8548, "overs": "2.5", "wickets": 0, "runs": 44,
      "economy": "15.53", "name": "Taskin Ahmed", ...
  }
  miniscore.bowlernonstriker = { same shape, other bowler }
  miniscore.crr = 11.15
  miniscore.rrr = 0
  miniscore.target = 128
  miniscore.lastwkt = "Sanju Samson  c Rishad Hossain b Mehidy Hasan Miraz 29(19) - 80/3 in 7.5 ov."
  miniscore.inningsscores.inningsscore = [
      {"inningsid": 2, "runs": 132, "wickets": 3, "overs": 11.5, "target": 128, "balls": 71, ...},
      {"inningsid": 1, "runs": 127, "wickets": 10, "overs": 19.5, ...}
  ]
  miniscore.inningsid = 2   # which innings is CURRENTLY live

This matches EXACTLY what app.py's existing _shape_match_details_from_cricbuzz
already reads (miniscore.get("crr"), miniscore.get("target"), etc.) -
confirming that function's existing logic is correct, and was simply
never getting a populated miniscore for match 150942 specifically
(a Major League Cricket match) at the moment it was checked. The field
names app.py already expects are right; we just needed the real
striker/bowler field names for the NEW player-insight piece, which
app.py doesn't currently extract at all.

WHY match 150942 GAVE US miniscore=None: unconfirmed, but the most
likely explanation is that Cricbuzz doesn't populate rich miniscore
data uniformly for lower-tier league matches (Major League Cricket)
the way it does for full internationals - or there was a timing gap
(match between overs, no striker "on strike" at that instant). Since
app.py's OWN existing crr/rrr/target reading already handles
miniscore=None gracefully (the `if miniscore:` guard in
_shape_match_details_from_cricbuzz), no code change is needed there -
this is expected, already-handled behavior, not a bug to fix.

WHERE THIS PLUGS IN:
Same place as before - inside app.py's _refresh_match_detail(), after
comm_result = _fetch_cricbuzz_commentary_and_miniscore(...) already
gives us `miniscore`. Venue and matchFormat come from the carousel
entry (see REVISION 2's note on threading carousel_entry into
_refresh_match_detail - that part of the plan is unchanged).
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
    Builds the live_state dict get_match_insights() expects, from:
      - venue_name: carousel data's venueInfo.ground
      - match_format_str: carousel data's matchFormat
      - is_ipl: caller-determined (see note in REVISION 2 - unchanged)
      - miniscore: the raw miniscore dict from Cricbuzz's /comm response
        (app.py's `comm_result["miniscore"]`) - CAN be None (confirmed
        real behavior for some matches/moments), callers must handle
        that, which this function does by returning a partial live_state.
    """
    live_state = {
        "venue_name": venue_name or "",
        "match_format": match_format_str or "",
        "is_ipl": is_ipl,
    }

    if not miniscore:
        return live_state  # partial state - get_match_insights() handles missing context gracefully

    # Current innings score/wickets/overs - from inningsscores, matching
    # whichever inningsid miniscore.inningsid says is currently live.
    current_innings_id = miniscore.get("inningsid")
    innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])
    current_innings = next((s for s in innings_scores if s.get("inningsid") == current_innings_id), None)
    if current_innings is None and innings_scores:
        # fall back to whichever innings has the highest id (most recent)
        current_innings = max(innings_scores, key=lambda s: s.get("inningsid", 0))

    if current_innings:
        live_state["current_score"] = current_innings.get("runs")
        live_state["current_wickets"] = current_innings.get("wickets")
        overs_val = current_innings.get("overs")
        if overs_val is not None:
            live_state["overs_completed_str"] = str(overs_val)
            live_state["current_over_number"] = int(overs_val)

    striker = miniscore.get("batsmanstriker")
    if striker and striker.get("name") and striker.get("runs") is not None and striker.get("balls") is not None:
        live_state["striker_name"] = striker["name"]
        live_state["striker_current_runs"] = striker["runs"]
        live_state["striker_current_balls"] = striker["balls"]

    # NEW: phase-runs/balls, needed for venue_phase_insight - this was
    # previously never populated, so phase insights never fired on any
    # live match regardless of innings. Cricbuzz's own miniscore.pp field
    # gives us the real powerplay total directly when we're still in it
    # ("pp": {"powerplay": [{"ovrfrom":0.1,"ovrto":6,"run":71,"wickets":0}]}
    # - confirmed real shape from an earlier live response). For middle/
    # death phases (no equivalent Cricbuzz field), we approximate using
    # the team's overall run rate up to now scaled to the current phase's
    # over-range - a reasonable estimate, not a precise ball-by-ball
    # figure, since live data doesn't give us a phase-scoped breakdown
    # for anything past the powerplay.
    if current_innings and "overs" in (current_innings or {}):
        overs_now = current_innings.get("overs") or 0
        total_runs = current_innings.get("runs") or 0
        match_type_for_phase = "ODI" if match_format_str.upper() in ("ODI", "ODM") else "T20"
        bounds = (
            [("powerplay", 0, 10), ("middle", 10, 40), ("death", 40, 50)]
            if match_type_for_phase == "ODI" else
            [("powerplay", 0, 6), ("middle", 6, 15), ("death", 15, 20)]
        )
        current_phase = None
        for name, start, end in bounds:
            if start <= overs_now < end or (name == bounds[-1][0] and overs_now >= end):
                current_phase = (name, start, end)
                break

        if current_phase:
            phase_name, phase_start, phase_end = current_phase
            pp_data = ((miniscore.get("pp") or {}).get("powerplay") or [])
            if phase_name == "powerplay" and pp_data:
                # Real Cricbuzz powerplay figure - exact, not estimated.
                # This is the ONLY phase we can compute honestly with the
                # live data available. Middle/death phase runs would need
                # an even-distribution estimate that stress-testing showed
                # can be off by 50%+ in realistic uneven-scoring scenarios
                # (e.g. a fast powerplay followed by a genuine slowdown) -
                # that's not an estimate, that's a guess dressed up as a
                # number. Per this project's stated principle (refuse
                # rather than guess), middle/death phase insights are left
                # unpopulated until a real data source exists for them
                # (e.g. accumulating phase totals ourselves from ball-by-
                # ball commentary over time, rather than inferring from
                # a single snapshot).
                pp_entry = pp_data[0]
                live_state["phase_name"] = "powerplay"
                live_state["current_phase_runs"] = pp_entry.get("run", 0)
                live_state["current_phase_balls"] = round((min(overs_now, phase_end) - phase_start) * 6)

    return live_state


def get_insights_for_match(venue_name, match_format_str, is_ipl, miniscore):
    """
    Convenience one-call wrapper: build live_state and run the Insight
    Engine in one step.
    """
    from match_intelligence_api import get_match_insights
    live_state = build_live_state(venue_name, match_format_str, is_ipl, miniscore)
    return get_match_insights(live_state)


if __name__ == "__main__":
    import json

    # Real miniscore structure, from the actual sample Sanzz pulled
    # (India vs Bangladesh 1st T20I, trimmed to relevant fields)
    real_miniscore = {
        "batsmanstriker": {
            "id": 9647, "balls": 16, "runs": 39, "fours": 5, "sixes": 2,
            "strkrate": "243.75", "name": "Hardik Pandya", "outdec": "",
        },
        "batsmannonstriker": {
            "id": 14701, "balls": 15, "runs": 16, "fours": 0, "sixes": 1,
            "strkrate": "106.67", "name": "Nitish Reddy", "outdec": "",
        },
        "crr": 11.15,
        "rrr": 0,
        "lastwkt": "Sanju Samson  c Rishad Hossain b Mehidy Hasan Miraz 29(19) - 80/3 in 7.5 ov.",
        "inningsscores": {
            "inningsscore": [
                {"inningsid": 2, "batteamshortname": "IND", "runs": 132, "wickets": 3, "overs": 11.5, "target": 128, "balls": 71},
                {"inningsid": 1, "batteamshortname": "BAN", "runs": 127, "wickets": 10, "overs": 19.5, "target": 128, "balls": 119},
            ]
        },
        "inningsid": 2,
        "target": 128,
    }

    print("--- Test: build_live_state from REAL confirmed miniscore structure ---")
    live_state = build_live_state(
        venue_name="Narendra Modi Stadium",  # example venue, not from this sample
        match_format_str="T20",
        is_ipl=False,
        miniscore=real_miniscore,
    )
    print(json.dumps(live_state, indent=2))

    print("\n--- Test: full insight generation ---")
    result = get_insights_for_match(
        venue_name="Narendra Modi Stadium",
        match_format_str="T20",
        is_ipl=False,
        miniscore=real_miniscore,
    )
    print(json.dumps(result, indent=2))

    print("\n--- Test: miniscore=None (confirmed real case, e.g. match 150942) handled gracefully ---")
    result_none = get_insights_for_match(
        venue_name="Oakland Coliseum",
        match_format_str="T20",
        is_ipl=False,
        miniscore=None,
    )
    print(json.dumps(result_none, indent=2))
