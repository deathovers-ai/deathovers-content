"""
Epic 6 integration guide for app.py — REVISION 4 (adds player-name resolution)

Confirmed real field names from an actual RapidAPI response:
  miniscore.batsmanstriker = {"name": ..., "runs": ..., "balls": ..., ...}
  miniscore.batsmannonstriker = { same shape }
  miniscore.crr, miniscore.rrr, miniscore.target
  miniscore.inningsscores.inningsscore = [{"inningsid":, "runs":, "wickets":, "overs":, ...}]
  miniscore.inningsid = which innings is currently live

REVISION 4 change: Cricbuzz sends full player names (e.g. "Virat Kohli"),
but player_stats.json is keyed by Cricsheet's naming convention, which is
usually "<first-initial(s)> <Surname>" (e.g. "V Kohli") and only
occasionally a full name outright (e.g. "MS Dhoni", "Rohit Sharma" both
appear as literal keys, inconsistently, depending on how Cricsheet scored
that player). Previously nothing bridged these two naming schemes, so
striker_name lookups into player_stats.json almost always missed and
player-form insights silently never appeared. resolve_player_name() below
adds that bridge - see its docstring for the matching strategy and why it
refuses rather than guesses on anything ambiguous.
"""
import os
import sys
from collections import defaultdict

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


# ---------------------------------------------------------------------------
# Player name resolution: Cricbuzz full name -> player_stats.json key
# ---------------------------------------------------------------------------
# Built once per engine instance (keys never change at runtime), then reused
# for every live lookup. Kept as module-level state keyed off the specific
# player_stats dict object so a test/alternate engine with different stats
# doesn't collide with the cache from a real one.
_signature_index_cache = {}  # id(player_stats) -> {(first_initial, surname_lower): [keys]}


def _build_signature_index(player_stats):
    """
    Groups every player_stats.json key by (first-initial, surname) so a
    live full name can be resolved to the matching Cricsheet-style key.
    Ambiguous signatures (multiple different players sharing the same
    first-initial + surname, e.g. "R Sharma" could be Rohit or Ravi or
    Riyan Sharma) are kept as multi-entry lists deliberately - the lookup
    function below only accepts a signature match when exactly one
    candidate exists, otherwise it refuses.
    """
    index = defaultdict(list)
    for key in player_stats.keys():
        parts = key.split()
        if len(parts) < 2:
            continue
        surname = parts[-1].lower()
        first_initial = parts[0][0].lower()
        index[(first_initial, surname)].append(key)
    return dict(index)


def _get_signature_index(player_stats):
    cache_key = id(player_stats)
    if cache_key not in _signature_index_cache:
        _signature_index_cache[cache_key] = _build_signature_index(player_stats)
    return _signature_index_cache[cache_key]


def resolve_player_name(raw_name, player_stats):
    """
    Resolve a live-provider player name (Cricbuzz's full "Virat Kohli"
    style) to the key used in player_stats.json (Cricsheet's abbreviated
    style, usually "V Kohli", occasionally a full name as-is).

    Strategy, in order, stopping at the first hit:
      1. Exact match - some players (MS Dhoni, Rohit Sharma, Shubman Gill)
         are already keyed by their full/near-full name in player_stats.json,
         so try this first and skip the rest of the work if it lands.
      2. Signature match (first-initial + surname) - resolves the common
         case ("Virat Kohli" -> "V Kohli", "Jasprit Bumrah" -> "JJ Bumrah")
         but ONLY if exactly one player_stats.json entry shares that
         signature. If two+ different players share it (e.g. "R Sharma" is
         ambiguous between Rohit/Ravi/Riyan Sharma), this refuses rather
         than guessing - a wrong player-form comparison is worse than no
         comparison at all, same philosophy as the rest of this module.

    Returns the resolved key, or None if no safe match was found.
    """
    if not raw_name:
        return None

    if raw_name in player_stats:
        return raw_name

    parts = raw_name.strip().split()
    if len(parts) < 2:
        return None

    surname = parts[-1].lower()
    first_initial = parts[0][0].lower()
    index = _get_signature_index(player_stats)
    candidates = index.get((first_initial, surname))

    if candidates and len(candidates) == 1:
        return candidates[0]

    return None


def build_live_state(venue_name, match_format_str, is_ipl, miniscore, player_stats=None):
    """
    Builds the live_state dict get_match_insights() expects.

    player_stats is optional - when provided (get_insights_for_match passes
    the engine's loaded player_stats through), the live striker name is
    resolved against it via resolve_player_name() before being placed in
    live_state, so downstream lookups in insight_engine.py hit the right
    key. When omitted, the raw Cricbuzz name is passed through unchanged
    (preserves old behavior for any other caller).
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
        raw_striker_name = striker["name"]
        resolved_name = (
            resolve_player_name(raw_striker_name, player_stats)
            if player_stats is not None
            else raw_striker_name
        )
        if resolved_name:
            live_state["striker_name"] = resolved_name
            live_state["striker_current_runs"] = striker["runs"]
            live_state["striker_current_balls"] = striker["balls"]
        # If resolution failed, we deliberately omit striker_name/runs/balls
        # entirely rather than passing through a name that won't match
        # anything - generate_all() only attempts the player-form insight
        # when all three of those keys are present, so this correctly
        # results in "no player insight this cycle" instead of a wasted
        # or incorrect lookup downstream.

    return live_state


def get_insights_for_match(venue_name, match_format_str, is_ipl, miniscore):
    """
    Convenience one-call wrapper: build live_state and run the Insight
    Engine in one step. Passes the engine's loaded player_stats through to
    build_live_state so the live striker name gets resolved against it.
    """
    from match_intelligence_api import get_match_insights
    engine = get_engine()
    live_state = build_live_state(venue_name, match_format_str, is_ipl, miniscore, player_stats=engine.player_stats)
    return get_match_insights(live_state)
