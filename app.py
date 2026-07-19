"""
app.py — DeathOvers live-data backend (v5)

Changes from v4:
  - Wired in the Intelligence Engine (Epic 6): /api/match-details/<id> now
    includes an "intelligence" key with venue/player insights, built from
    the Cricsheet-derived Context Repository + Insight Engine.
  - Intelligence module import is defensive: if intelligence/output/context
    JSON files are missing or the module fails to import, the app logs a
    warning and keeps serving live scores normally (no crash, no regression
    to existing functionality).
  - _refresh_match_detail now looks up the carousel entry for a match to get
    venue/format for the intelligence bridge (carousel data was already
    being fetched separately; this just also uses it here).

Changes from v3:
  - Global RapidAPI call budget (shared across all Cricbuzz calls, not per-match)
  - Batter dismissal text + bowler name now mapped through to the frontend
  - CricketData fallback now actually parses completed-match scores instead of
    hard-coding them to null
  - Live-matches polling backs off automatically when there are zero live matches
  - /api/quota-status debug route
  - On-demand detail fetch on first view is now budget-gated instead of unlimited
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import logging
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify
from flask_cors import CORS

from team_crests import crest_image_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("deathovers-backend")

# ---------------------------------------------------------------------------
# Intelligence Engine (Epic 6) - defensive import
# ---------------------------------------------------------------------------
# If intelligence/output/context/*.json isn't present in this deploy (e.g.
# not yet committed, or a fresh clone that hasn't run the parser locally),
# this must NOT take down the whole app - live scores are the core product,
# insights are additive. Any failure here just means the "intelligence" key
# is omitted from match-details responses until it's fixed.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "intelligence", "parser"))
try:
    from app_integration import get_insights_for_match
    _INTELLIGENCE_AVAILABLE = True
    log.info("Intelligence Engine loaded successfully.")
except Exception as _intel_import_err:
    get_insights_for_match = None
    _INTELLIGENCE_AVAILABLE = False
    log.warning(
        "Intelligence Engine unavailable at startup (%s) - /api/match-details will "
        "omit the 'intelligence' key until this is resolved.", _intel_import_err
    )

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CRICKETDATA_API_KEY = os.environ.get("CRICKETDATA_API_KEY", "")
CRICKETDATA_BASE = "https://api.cricapi.com/v1"

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
CRICBUZZ_HOST = "cricbuzz-cricket2.p.rapidapi.com"
CRICBUZZ_BASE = f"https://{CRICBUZZ_HOST}"

REFRESH_INTERVAL_SECONDS = int(os.environ.get("REFRESH_INTERVAL_SECONDS", 900))
NO_LIVE_BACKOFF_SECONDS = int(os.environ.get("NO_LIVE_BACKOFF_SECONDS", 1800))  # when nothing is live
REQUEST_TIMEOUT_SECONDS = 10

# RapidAPI free-tier daily cap for cricbuzz-cricket2. Set a few calls below your
# actual plan limit as a safety margin. Override via env var if your plan differs.
RAPIDAPI_DAILY_CALL_CAP = int(os.environ.get("RAPIDAPI_DAILY_CALL_CAP", 450))

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache = {
    "live_and_recent": [],
    "last_refreshed": None,
    "last_error": None,
}

_detail_cache_lock = threading.Lock()
_detail_cache: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Global RapidAPI quota tracker
# ---------------------------------------------------------------------------
# Every single call to _cricbuzz_get is counted here, regardless of caller.
# This is the one source of truth for "how many RapidAPI calls have we made today".

_quota_lock = threading.Lock()
_quota = {
    "calls_today": 0,
    "day_started": datetime.now(timezone.utc).date().isoformat(),
    "blocked_calls": 0,
}


def _quota_reset_if_new_day() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if _quota["day_started"] != today:
        _quota["day_started"] = today
        _quota["calls_today"] = 0
        _quota["blocked_calls"] = 0


def _quota_has_budget() -> bool:
    with _quota_lock:
        _quota_reset_if_new_day()
        return _quota["calls_today"] < RAPIDAPI_DAILY_CALL_CAP


def _quota_consume() -> None:
    with _quota_lock:
        _quota_reset_if_new_day()
        _quota["calls_today"] += 1


def _quota_note_blocked() -> None:
    with _quota_lock:
        _quota_reset_if_new_day()
        _quota["blocked_calls"] += 1


def _quota_snapshot() -> dict:
    with _quota_lock:
        _quota_reset_if_new_day()
        return {
            "callsToday": _quota["calls_today"],
            "dailyCap": RAPIDAPI_DAILY_CALL_CAP,
            "remaining": max(0, RAPIDAPI_DAILY_CALL_CAP - _quota["calls_today"]),
            "blockedCalls": _quota["blocked_calls"],
            "dayStarted": _quota["day_started"],
        }


# ---------------------------------------------------------------------------
# Fetch Helpers
# ---------------------------------------------------------------------------

def _cricketdata_get(path: str, params: dict) -> dict | None:
    if not CRICKETDATA_API_KEY:
        return None
    params = {**params, "apikey": CRICKETDATA_API_KEY}
    url = f"{CRICKETDATA_BASE}/{path}"
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        return data if data.get("status") == "success" else None
    except Exception as e:
        log.error("CricketData request failed: %s", e)
        return None


def _cricbuzz_get(path: str, params: dict | None = None) -> dict | None:
    """All Cricbuzz/RapidAPI calls funnel through here. This is the single
    choke point for the global daily quota — nothing bypasses it."""
    if not RAPIDAPI_KEY:
        return None
    if not _quota_has_budget():
        _quota_note_blocked()
        log.warning("RapidAPI daily quota exhausted (%s calls) — blocking call to %s", RAPIDAPI_DAILY_CALL_CAP, path)
        return None

    url = f"{CRICBUZZ_BASE}{path}"
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": CRICBUZZ_HOST}
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=REQUEST_TIMEOUT_SECONDS)
        _quota_consume()  # count the call whether it succeeds or fails — it still hit RapidAPI
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("Cricbuzz request failed (%s): %s", path, e)
        return None


# ---------------------------------------------------------------------------
# Shapers & Parsers
# ---------------------------------------------------------------------------

def _resolve_commentary_placeholders(text: str, commentary_formats: list) -> str:
    if "$" not in text:
        return text
    replacements = {}
    for fmt in commentary_formats or []:
        for item in fmt.get("value", []) or []:
            token = item.get("id")
            value = item.get("value")
            if token and value is not None:
                replacements[token] = value
    result = text
    for token, value in replacements.items():
        result = result.replace(token, value)
    result = re.sub(r"B\d+\$", "", result)
    result = " ".join(result.split())
    cleaned = re.sub(r".*?(?:caught by [^!]*!!|run out!!|bowled!!|stumped!!)\s*", "", result, flags=re.IGNORECASE)
    if cleaned and cleaned != result:
        result = cleaned.strip()
    else:
        result = re.sub(r"^(.*?),\s*out\s+", r"\1, ", result, count=1, flags=re.IGNORECASE)
    return result


def _is_system_announcement(text: str) -> bool:
    t = text.strip().lower()
    if any(phrase in t for phrase in ("thats out!!", "caught!!", "bowled!!", "run out!!", "stumped!!")) and len(t) < 60:
        return True
    if any(phrase in t for phrase in ("comes to the crease", "is back into the attack", "into the attack", "time for drinks")):
        return True
    return False


def _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id: str, innings_id: int = 1, tms: int | None = None) -> dict:
    """NEW: tms is the pagination cursor Cricbuzz's /comm endpoint uses -
    pass the oldest timestamp seen so far to get the NEXT (older) page.
    Leave None for the first/most-recent page. Confirmed working against
    a real RapidAPI response (verified in the playground before building
    this - paginating with tms correctly returned earlier overs)."""
    params = {"iid": innings_id}
    if tms:
        params["tms"] = tms
    data = _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/comm", params=params)
    if data is None:
        return {"commentary": [], "miniscore": None}

    entries = data.get("comwrapper", [])
    miniscore = data.get("miniscore")
    shaped = []

    for entry in entries:
        c = entry.get("commentary", {})
        raw_text = (c.get("commtxt") or "").strip()
        if not raw_text:
            continue
        text = _resolve_commentary_placeholders(raw_text, c.get("commentaryformats", []))
        if _is_system_announcement(text):
            continue

        event = (c.get("eventtype") or "NONE").upper()
        if "WICKET" in event:
            ctype = "wicket"
        elif "SIX" in event:
            ctype = "six"
        elif "FOUR" in event:
            ctype = "four"
        elif text.lower().startswith("no run"):
            ctype = "dot"
        else:
            ctype = "run"

        over_label = ""
        ballnbr = c.get("ballnbr", 0)
        overnum = c.get("overnum", 0)
        if isinstance(overnum, (int, float)) and overnum:
            over_label = f"{overnum:.1f}"
        elif isinstance(ballnbr, (int, float)) and ballnbr:
            over_label = f"{(ballnbr - 1) // 6}.{(ballnbr - 1) % 6 + 1}"

        shaped.append({
            "over": over_label,
            "type": ctype,
            "text": text,
            "ballnbr": ballnbr if isinstance(ballnbr, (int, float)) else 0,
            "timestamp": c.get("timestamp", 0),
            "innings": innings_id,  # NEW: prevents ballnbr collisions between innings 1 and 2 during merge/dedup
        })
    # NOTE: previously this hard-capped to the most recent 30 balls (shaped[:30]),
    # which meant the frontend could never show commentary older than ~5 overs back —
    # not a scroll bug, the data was simply discarded here. We now return everything
    # Cricbuzz gives us in this call; accumulation across refreshes (in
    # _refresh_match_detail) is what builds the full-innings history over time.
    return {"commentary": shaped, "miniscore": miniscore, "raw_comwrapper": entries}


# Backfill up to this many pages per innings (each page = ~1 RapidAPI call).
# A full T20 innings is ~120-150 balls at ~20 balls/page -> 6-8 pages is
# plenty; ODI innings are longer but we cap here regardless to protect
# the daily quota - a few overs of missing very-early commentary is a
# much smaller problem than running out of API budget for live scores,
# which is the core product.
MAX_BACKFILL_PAGES = 8
# Never spend more than this fraction of the remaining daily quota on one
# backfill operation - keeps one match's history fetch from starving
# every other match's live updates.
MAX_BACKFILL_QUOTA_FRACTION = 0.15


def _backfill_full_commentary(cricbuzz_match_id: str, innings_id: int, first_page_result: dict) -> list[dict]:
    """
    Paginates backward through Cricbuzz's /comm endpoint using the `tms`
    cursor until the start of the innings is reached (ballnbr hits 1) or
    a safety limit is hit. Called ONCE per match/innings (the caller is
    responsible for only invoking this the first time a match is opened,
    not on every scheduled refresh) - see _refresh_match_detail for the
    "have we backfilled this match already" check.
    """
    all_commentary = list(first_page_result["commentary"])
    if not all_commentary:
        return all_commentary

    oldest_ballnbr = min((c["ballnbr"] for c in all_commentary if c["ballnbr"]), default=0)
    oldest_timestamp = min((c["timestamp"] for c in all_commentary if c["timestamp"]), default=0)

    pages_fetched = 0
    while oldest_ballnbr > 1 and pages_fetched < MAX_BACKFILL_PAGES and oldest_timestamp:
        snap = _quota_snapshot()
        if snap["remaining"] < RAPIDAPI_DAILY_CALL_CAP * MAX_BACKFILL_QUOTA_FRACTION:
            log.warning("Stopping commentary backfill for match %s - protecting remaining quota (%s calls left)",
                        cricbuzz_match_id, snap["remaining"])
            break

        page = _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id, innings_id=innings_id, tms=oldest_timestamp)
        pages_fetched += 1
        new_entries = page["commentary"]
        if not new_entries:
            break  # no more history available

        new_oldest_ballnbr = min((c["ballnbr"] for c in new_entries if c["ballnbr"]), default=0)
        new_oldest_timestamp = min((c["timestamp"] for c in new_entries if c["timestamp"]), default=0)
        if new_oldest_timestamp == oldest_timestamp or new_oldest_ballnbr >= oldest_ballnbr:
            break  # not making progress - stop rather than loop forever

        all_commentary.extend(new_entries)
        oldest_ballnbr = new_oldest_ballnbr
        oldest_timestamp = new_oldest_timestamp

    log.info("Backfilled commentary for match %s innings %s: %s pages, %s total entries, reached ball %s",
              cricbuzz_match_id, innings_id, pages_fetched, len(all_commentary), oldest_ballnbr)
    return all_commentary


def _fetch_cricbuzz_scorecard(cricbuzz_match_id: str) -> dict | None:
    return _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/scard")


def _format_dismissal(batter: dict) -> str:
    """Builds a human-readable dismissal line, e.g. 'c Kohli b Bumrah', 'b Starc',
    'run out (Warner/Smith)', 'lbw b Cummins', or 'not out'."""
    outdec = (batter.get("outdec") or "").strip()
    if not outdec or outdec.lower() == "not out":
        return "not out"
    return outdec


def _shape_innings_from_cricbuzz(inn: dict) -> dict:
    batting = inn.get("batsman", [])
    bowling = inn.get("bowler", [])
    return {
        "team": inn.get("batteamname", ""),
        "score": f"{inn.get('score', '')}/{inn.get('wickets', '')}" if inn.get("score") is not None else "",
        "overs": str(inn.get("overs", "")),
        "batters": [
            {
                "name": b.get("name", "Unknown"),
                "r": b.get("runs", 0),
                "b": b.get("balls", 0),
                "sr": str(b.get("strkrate", "")),
                "dim": (b.get("outdec", "").lower() == "not out"),
                "dismissal": _format_dismissal(b),
            }
            for b in batting
        ],
        "bowlers": [
            {
                "name": bo.get("name", "Unknown"),
                "o": str(bo.get("overs", "")),
                "r": str(bo.get("runs", "")),
                "w": str(bo.get("wickets", "")),
                "eco": str(bo.get("economy", "")),
            }
            for bo in bowling
        ],
    }


def _extract_ball_tracker(miniscore: dict | None) -> list[dict]:
    """Parses the current over directly from Cricbuzz's overseplist.oversummary"""
    if not miniscore:
        return []
    oversep_list = miniscore.get("overseplist", {}).get("oversep", [])
    if not oversep_list:
        return []
    latest_over = oversep_list[0].get("oversummary", "").strip()
    if not latest_over:
        return []

    balls = []
    events = latest_over.split()
    for event in events:
        event_upper = event.upper()
        if "W" in event_upper and "WD" not in event_upper:
            ctype = "wicket"
            label = "W"
        elif "6" in event:
            ctype = "six"
            label = "6"
        elif "4" in event:
            ctype = "four"
            label = "4"
        elif event in ("0", "0."):
            ctype = "dot"
            label = "•"
        else:
            ctype = "run"
            label = event
        balls.append({"label": label, "type": ctype})
    return balls


def _shape_match_for_carousel(m: dict) -> dict:
    info = m.get("matchInfo", m)
    team1 = info.get("team1", {}) or {}
    team2 = info.get("team2", {}) or {}

    home_name = team1.get("teamName", team1.get("teamname", "TBD"))
    away_name = team2.get("teamName", team2.get("teamname", "TBD"))

    state = (info.get("state") or "").lower()
    if state in ("in progress", "innings break", "toss", "stumps"):
        status = "LIVE"
    elif state in ("complete", "abandoned", "no result"):
        status = "COMPLETED"
    else:
        status = "UPCOMING"

    def _fmt(score: dict | None) -> "dict | None":
        if not score:
            return None
        return {
            "score": f"{score.get('runs', score.get('r', 0))}/{score.get('wickets', score.get('w', 0))}",
            "info": f"{score.get('overs', score.get('o', 0))}",
        }

    match_score = info.get("matchScore") or {}
    # NEW: for Test matches, each team can have both inngs1 and inngs2 (their 1st
    # and 2nd innings — Cricbuzz's own inningsId numbering interleaves these across
    # teams, e.g. team1's innings are inningsId 1 and 3, team2's are 2 and 4, but
    # inngs1/inngs2 here just means "this team's first/second innings"). Previously
    # this always read inngs1, so once a team moved on to their 2nd innings, the
    # carousel card kept showing their old, final 1st-innings score — a real
    # confirmed bug, not just a hypothetical: a Test match currently in a team's
    # 2nd innings would show their completed 1st-innings total instead of the live one.
    team1_score_block = match_score.get("team1Score") or {}
    team2_score_block = match_score.get("team2Score") or {}
    home_score = team1_score_block.get("inngs2") or team1_score_block.get("inngs1")
    away_score = team2_score_block.get("inngs2") or team2_score_block.get("inngs1")

    raw_format = (info.get("matchFormat", info.get("matchformat", ""))).strip()
    match_format = raw_format.upper() if raw_format else "UNKNOWN"
    venue = info.get("venueInfo", info.get("venueinfo", {})) or {}
    venue_label = venue.get("ground", "") or info.get("seriesName", info.get("seriesname", ""))

    return {
        "id": info.get("matchId", info.get("matchid")),
        "venue": venue_label,
        "status": status,
        "matchName": f"{home_name} vs {away_name}",
        "matchFormat": match_format,
        "score": {"home": _fmt(home_score), "away": _fmt(away_score)},
        "chaseNote": info.get("status", ""),
        "teams": [home_name, away_name],
        "homeImageId": team1.get("imageId", team1.get("imageid")) or crest_image_id(home_name),
        "awayImageId": team2.get("imageId", team2.get("imageid")) or crest_image_id(away_name),
        # NEW: carry seriesName through so the intelligence bridge can detect IPL
        # matches (Cricbuzz's matchFormat field alone doesn't distinguish IPL from
        # a generic international T20).
        "seriesName": info.get("seriesName", info.get("seriesname", "")),
    }


def _latest_oversep_from_commentary(commentary_raw_entries: list[dict]) -> dict | None:
    """
    Find the most recent `oversep` block in the RAW (unshaped) comwrapper
    entries - these appear on the last ball of each over and contain the
    score/wickets/over at that exact moment. Commentary is fetched more
    granularly than miniscore is refreshed, so when the two disagree,
    commentary's oversep is the more trustworthy, more recent source -
    this is what fixes the live-score-vs-commentary mismatch (confirmed
    real: a live match showed CRR/score for over 10 while commentary had
    already reached over 16 - the two data points came from calls made at
    different instants during backfill pagination).
    """
    for entry in commentary_raw_entries:
        c = entry.get("commentary", {})
        oversep = c.get("oversep")
        if oversep:
            return oversep
    return None


def _shape_match_details_from_cricbuzz(scorecard_data: dict | None, commentary: list[dict], miniscore: dict | None, raw_comwrapper: list[dict] | None = None) -> dict:
    scorecard_list = (scorecard_data or {}).get("scorecard", [])

    def _find_innings(innings_id: int) -> dict | None:
        for inn in scorecard_list:
            if inn.get("inningsid") == innings_id:
                return inn
        return None

    # NEW: Test matches can have up to 4 innings (2 per side, in a follow-on or
    # standard 2-innings-per-team format). The old code only ever looked for
    # inningsid 1 and 2, so a Test match's 3rd/4th innings simply never appeared —
    # not a bug in the UI, the data was never fetched into the shape at all.
    # We build a generic `innings` list of however many innings actually exist in
    # the scorecard (1 to 4), each tagged with its inningsid, so the frontend can
    # render whatever count is real for this match's format.
    all_innings = []
    for innings_id in range(1, 5):
        raw = _find_innings(innings_id)
        if raw:
            shaped_inn = _shape_innings_from_cricbuzz(raw)
            shaped_inn["inningsId"] = innings_id
            all_innings.append(shaped_inn)

    # NEW: commentary-derived ground truth for "what's the current over/score
    # right now" - takes priority over scorecard/miniscore data when they
    # disagree, since commentary is the freshest granular source.
    latest_oversep = _latest_oversep_from_commentary(raw_comwrapper) if raw_comwrapper else None
    if latest_oversep:
        oversep_innings_id = latest_oversep.get("inningsid")
        for inn in all_innings:
            if inn["inningsId"] == oversep_innings_id:
                oversep_overnum = latest_oversep.get("overnum")
                oversep_score = latest_oversep.get("score")
                oversep_wickets = latest_oversep.get("wickets")
                if oversep_overnum is not None and oversep_score is not None:
                    inn["score"] = f"{oversep_score}/{oversep_wickets}"
                    inn["overs"] = str(oversep_overnum)

    toss_line = ""
    live_score = None
    if miniscore:
        innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])

        def _find_score(innings_id: int) -> dict | None:
            for s in innings_scores:
                if s.get("inningsid") == innings_id:
                    return s
            return None

        # NEW: overwrite live scores for every innings present, not just the first two —
        # keeps a Test match's 3rd/4th innings score current during live play too.
        for inn in all_innings:
            s = _find_score(inn["inningsId"])
            if s is not None:
                # Only apply miniscore's numbers if we do NOT already have a
                # more-recent commentary-derived override for this exact
                # innings (see latest_oversep block above) - otherwise
                # miniscore can overwrite the correct, fresher commentary
                # value with a stale one, re-introducing the mismatch.
                already_overridden = (
                    latest_oversep
                    and latest_oversep.get("inningsid") == inn["inningsId"]
                    and latest_oversep.get("overnum") is not None
                )
                if not already_overridden:
                    inn["score"] = f"{s.get('runs', 0)}/{s.get('wickets', 0)}"
                    inn["overs"] = str(s.get("overs", ""))

        s1 = _find_score(1)
        s2 = _find_score(2)

        def _fmt_live(s: dict | None, innings_id: int) -> dict:
            # NEW: prefer the commentary-derived override for this innings,
            # same reasoning as above - the scoreboard header should match
            # what the commentary feed is actually showing, not lag behind it.
            if latest_oversep and latest_oversep.get("inningsid") == innings_id and latest_oversep.get("overnum") is not None:
                return {
                    "score": f"{latest_oversep.get('score', 0)}/{latest_oversep.get('wickets', 0)}",
                    "info": str(latest_oversep.get("overnum")),
                }
            if not s:
                return {"score": "yet to bat", "info": ""}
            return {"score": f"{s.get('runs', 0)}/{s.get('wickets', 0)}", "info": str(s.get("overs", ""))}

        # liveScore.home/away stays as the most recent two innings for the compact
        # scoreboard header (which shows "current state", not full match history) —
        # full innings-by-innings detail lives in the `innings` array below instead.
        latest_two = all_innings[-2:] if len(all_innings) >= 2 else all_innings
        home_latest = latest_two[0] if len(latest_two) >= 1 else None
        away_latest = latest_two[1] if len(latest_two) >= 2 else None

        live_score = {
            "home": _fmt_live(_find_score(home_latest["inningsId"]), home_latest["inningsId"]) if home_latest else _fmt_live(s1, 1),
            "away": _fmt_live(_find_score(away_latest["inningsId"]), away_latest["inningsId"]) if away_latest else _fmt_live(s2, 2),
            "target": miniscore.get("target", 0),
            "crr": miniscore.get("crr", 0),
            "rrr": miniscore.get("rrr", 0),
            "lastWicket": miniscore.get("lastwkt", ""),
            "customStatus": miniscore.get("custstatus", ""),
        }
        toss_line = miniscore.get("lastwkt", "")

    ball_tracker = _extract_ball_tracker(miniscore)

    return {
        "toss": toss_line,
        "venue": "",
        "recentBalls": [],
        "commentary": commentary,
        "currentBowler": "",
        # NEW: generic innings list, works for 2-innings limited-overs and up to
        # 4-innings Test matches alike.
        "innings": all_innings,
        # Backward-compatible aliases — existing frontend code (and the death-overs
        # detection below) reads innings1/innings2 directly, so we keep populating
        # them from the first two entries. Safe for limited-overs (never more than
        # 2 anyway); for Tests, the frontend should prefer the new `innings` array.
        "innings1": all_innings[0] if len(all_innings) >= 1 else None,
        "innings2": all_innings[1] if len(all_innings) >= 2 else None,
        "liveScore": live_score,
        "ballTracker": ball_tracker,
    }


def _parse_cricketdata_innings_score(m: dict, team_index: int) -> "dict | None":
    """CricketData's currentMatches payload includes a top-level 'score' array,
    one entry per innings, each with an 'inning' label like 'India Inning 1' and
    r/w/o fields. We match by team name substring since there's no clean team id
    linkage in the free tier response."""
    teams = m.get("teams") or []
    if team_index >= len(teams):
        return None
    team_name = teams[team_index]
    score_entries = m.get("score") or []
    if not score_entries or not team_name:
        return None

    # Prefer the last innings for this team (handles Test matches with 2 innings each;
    # for limited-overs there's only one entry per team anyway).
    matches_for_team = [s for s in score_entries if team_name.split()[0].lower() in (s.get("inning", "") or "").lower()]
    if not matches_for_team:
        return None
    chosen = matches_for_team[-1]
    r = chosen.get("r", 0)
    w = chosen.get("w", 0)
    o = chosen.get("o", 0)
    return {"score": f"{r}/{w}", "info": str(o)}


def _shape_fill_match_from_cricketdata(m: dict) -> dict:
    teams = m.get("teams") or []
    home_name = teams[0] if len(teams) > 0 else "TBD"
    away_name = teams[1] if len(teams) > 1 else "TBD"
    raw_format = (m.get("matchType") or "").strip()

    home_score = _parse_cricketdata_innings_score(m, 0)
    away_score = _parse_cricketdata_innings_score(m, 1)

    return {
        "id": m.get("id"),
        "venue": m.get("venue", ""),
        "status": "COMPLETED" if m.get("matchEnded") else "UPCOMING",
        "matchName": m.get("name", f"{home_name} vs {away_name}"),
        "matchFormat": raw_format.upper() if raw_format else "UNKNOWN",
        "score": {"home": home_score, "away": away_score},
        "chaseNote": m.get("status", ""),
        "teams": [home_name, away_name],
        "homeImageId": crest_image_id(home_name),
        "awayImageId": crest_image_id(away_name),
        "seriesName": "",
    }


def _iter_cricbuzz_matches(list_payload: dict | None):
    if not list_payload:
        return
    for type_block in list_payload.get("typeMatches", []):
        for series in type_block.get("seriesMatches", []):
            wrapper = series.get("seriesAdWrapper", {})
            for match in wrapper.get("matches", []):
                info = match.get("matchInfo", {})
                if "matchScore" in match:
                    info = {**info, "matchScore": match["matchScore"]}
                if info:
                    yield info


def _refresh_live_matches() -> None:
    live_data = _cricbuzz_get("/matches/v1/live")
    live_shaped = [_shape_match_for_carousel(info) for info in _iter_cricbuzz_matches(live_data)]
    live_ids_by_teams = {tuple(sorted(m["teams"])) for m in live_shaped}

    cricketdata_data = _cricketdata_get("currentMatches", {"offset": 0})
    fill_shaped = []
    if cricketdata_data is not None:
        for m in cricketdata_data.get("data", []):
            teams = m.get("teams") or []
            if len(teams) < 2:
                continue
            if m.get("matchStarted") and not m.get("matchEnded"):
                continue
            if tuple(sorted(teams[:2])) in live_ids_by_teams:
                continue
            fill_shaped.append(_shape_fill_match_from_cricketdata(m))

    shaped = live_shaped + fill_shaped

    if live_data is None and cricketdata_data is None:
        with _cache_lock:
            _cache["last_error"] = f"refresh failed at {datetime.now(timezone.utc).isoformat()}"
        return

    with _cache_lock:
        _cache["live_and_recent"] = shaped
        _cache["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        _cache["last_error"] = None


# Max commentary entries retained per match, across both innings combined.
# A T20 innings is ~120-150 legal-delivery events plus wides/no-balls/wickets;
# 350 comfortably covers both innings of a full match with headroom.
MAX_COMMENTARY_ENTRIES = 350


def _merge_commentary(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merges freshly-fetched commentary into what we already had cached, instead
    of overwriting it. Cricbuzz's /comm endpoint only returns a recent window each
    call, so without this, older overs vanish from the feed every refresh even
    though nothing is wrong with scrolling — the data was just gone. Dedupes by
    ballnbr (falls back to the over+text pair if ballnbr is missing/zero), keeps
    newest-first order, and caps total size so memory doesn't grow unbounded over
    a long match."""
    seen_keys = set()
    merged = []
    # New entries first so the freshest data wins if Cricbuzz ever revises a ball's text.
    for entry in new + existing:
        key = (entry.get("innings", 1), entry.get("ballnbr")) if entry.get("ballnbr") else (entry.get("innings", 1), entry.get("over"), entry.get("text"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append(entry)

    # Sort by innings first (2nd innings entries on top when present), then by ball number within each.
    merged.sort(key=lambda e: (e.get("innings", 1), e.get("ballnbr", 0)), reverse=True)
    return merged[:MAX_COMMENTARY_ENTRIES]


def _synthesize_miniscore_from_shaped_innings(shaped: dict) -> dict | None:
    """
    Fallback for when Cricbuzz's real `miniscore` comes back None/empty
    (a confirmed real, intermittent failure mode - not our bug, a gap in
    the live data provider). shaped["innings1"]/["innings2"] are already
    correctly populated by this point via the commentary-derived
    _latest_oversep_from_commentary override (added earlier), even when
    miniscore itself is missing - e.g. score "163/0", overs "24.6" showed
    correctly in a real match where miniscore was None.

    Builds a minimal dict in the SAME SHAPE build_live_state() expects
    from a real miniscore (inningsscores.inningsscore list, inningsid),
    using whichever shaped innings is currently being batted (the one
    without a completed/"yet to bat" score). Returns None if neither
    innings has usable data either - in which case there's genuinely
    nothing to build insights from, and the Insight Engine correctly
    stays silent.
    """
    import re as _re

    def _parse_score_overs(inn: dict | None):
        if not inn or not inn.get("score") or inn.get("score") == "yet to bat":
            return None
        m = _re.match(r"(\d+)/(\d+)", inn["score"])
        if not m:
            return None
        runs, wickets = int(m.group(1)), int(m.group(2))
        try:
            overs = float(inn.get("overs") or 0)
        except (ValueError, TypeError):
            overs = 0.0
        return {"runs": runs, "wickets": wickets, "overs": overs, "innings_id": inn.get("inningsId", 1)}

    inn1_data = _parse_score_overs(shaped.get("innings1"))
    inn2_data = _parse_score_overs(shaped.get("innings2"))
    # Currently-batting innings is whichever has data and isn't finished -
    # simplest reliable signal available here is just "the later one that
    # has data", since a completed innings1 would already show inn2 batting.
    current = inn2_data or inn1_data
    if not current:
        return None

    return {
        "inningsscores": {
            "inningsscore": [
                {"inningsid": current["innings_id"], "runs": current["runs"],
                 "wickets": current["wickets"], "overs": current["overs"]}
            ]
        },
        "inningsid": current["innings_id"],
    }


def _attach_intelligence(shaped: dict, carousel_entry: dict | None, miniscore: dict | None) -> None:
    """
    Mutates `shaped` in place, adding an "intelligence" key with venue/player
    insights - or a clean empty/error shape if unavailable, so the frontend
    never has to special-case a missing key vs an empty insights list.
    Never raises - any failure here should degrade to no insights, not break
    the whole match-details response.

    NEW: falls back to a synthetic miniscore built from shaped["innings1"/
    "innings2"] when the real miniscore is missing/empty - this is what
    fixes the confirmed real case where venue/format resolve correctly
    (Lord's, ODI, zero warnings) but insights still came back empty,
    because miniscore was None for that poll even though the score WAS
    actually available via the commentary-derived innings data.
    """
    if not _INTELLIGENCE_AVAILABLE:
        shaped["intelligence"] = {"insights": [], "meta": {"available": False}}
        return
    if not carousel_entry:
        shaped["intelligence"] = {"insights": [], "meta": {"available": True, "warnings": ["no carousel entry for this match"]}}
        return
    try:
        venue_name = carousel_entry.get("venue", "")
        match_format = carousel_entry.get("matchFormat", "")
        series_name = carousel_entry.get("seriesName", "")
        is_ipl = "indian premier league" in (series_name + " " + venue_name).lower()

        effective_miniscore = miniscore
        used_fallback = False
        has_usable_scores = bool(
            miniscore and (miniscore.get("inningsscores") or {}).get("inningsscore")
        )
        if not has_usable_scores:
            synthetic = _synthesize_miniscore_from_shaped_innings(shaped)
            if synthetic:
                effective_miniscore = synthetic
                used_fallback = True

        result = get_insights_for_match(venue_name, match_format, is_ipl, effective_miniscore)
        if used_fallback:
            result.setdefault("meta", {})["score_source"] = "commentary_fallback"
        shaped["intelligence"] = result
    except Exception as e:
        log.error("Intelligence Engine failed for this match: %s", e)
        shaped["intelligence"] = {"insights": [], "meta": {"available": True, "error": str(e)}}


def _refresh_match_detail(match_id: str) -> None:
    cricbuzz_match_id = str(match_id)
    if not cricbuzz_match_id:
        return

    # NEW: look up this match's carousel entry (already cached from
    # _refresh_live_matches) to get venue/format/seriesName for the
    # intelligence bridge. Carousel data doesn't require an extra API call -
    # it's already sitting in _cache from the periodic live-matches refresh.
    with _cache_lock:
        carousel_entry = next(
            (m for m in _cache["live_and_recent"] if str(m.get("id")) == str(match_id)),
            None
        )

    with _detail_cache_lock:
        already_backfilled = (match_id in _detail_cache) and _detail_cache[match_id].get("backfilled_innings", set())
        backfilled_innings = set(already_backfilled) if already_backfilled else set()

    comm_result = _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id, innings_id=1)
    # NEW: on the FIRST fetch for this match/innings only, paginate backward
    # through /comm using the tms cursor to backfill full innings history -
    # this is what fixes commentary only ever showing a recent chunk instead
    # of starting from ball 1. Subsequent refreshes skip this (rely on the
    # existing incremental _merge_commentary instead) so we don't re-spend
    # quota re-fetching history we already have cached.
    if 1 not in backfilled_innings:
        comm_result["commentary"] = _backfill_full_commentary(cricbuzz_match_id, 1, comm_result)
        backfilled_innings.add(1)
    commentary = comm_result["commentary"]
    miniscore = comm_result["miniscore"]
    raw_comwrapper = comm_result.get("raw_comwrapper", [])
    scorecard_data = _fetch_cricbuzz_scorecard(cricbuzz_match_id)

    # NEW: previously this only ever checked "does innings 2 exist?" and fetched it
    # if so — meaning a Test match's 3rd/4th innings commentary was never fetched at
    # all, since the code never looked past inningsid 2. We now find whichever
    # innings is actually the highest/most-recent one reported by Cricbuzz's
    # miniscore (works for 2-innings limited-overs and up to 4-innings Tests alike)
    # and fetch that one specifically, since that's where live commentary is
    # actually happening right now.
    if miniscore:
        innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])
        reported_innings_ids = [s.get("inningsid") for s in innings_scores if s.get("inningsid")]
        current_innings_id = max(reported_innings_ids) if reported_innings_ids else 1

        if current_innings_id > 1:
            comm_result_current = _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id, innings_id=current_innings_id)
            if current_innings_id not in backfilled_innings and comm_result_current["commentary"]:
                comm_result_current["commentary"] = _backfill_full_commentary(
                    cricbuzz_match_id, current_innings_id, comm_result_current
                )
                backfilled_innings.add(current_innings_id)
            if comm_result_current["commentary"]:
                # Combine with innings-1 commentary rather than discarding it — the
                # merge step below dedupes/sorts by (innings, ballnbr) so entries
                # from every innings coexist correctly instead of overwriting each other.
                commentary = comm_result_current["commentary"] + commentary
                miniscore = comm_result_current["miniscore"] or miniscore
                # NEW: prefer the current (later) innings' raw entries for the
                # mismatch-fix logic, since that's where live play is happening.
                raw_comwrapper = comm_result_current.get("raw_comwrapper", []) or raw_comwrapper

    # Merge with whatever commentary we already have cached for this match instead
    # of replacing it outright, so scrolling back can reach the start of the innings.
    with _detail_cache_lock:
        prior_entry = _detail_cache.get(match_id)
    prior_commentary = (prior_entry or {}).get("data", {}).get("commentary", []) if prior_entry else []
    commentary = _merge_commentary(prior_commentary, commentary)

    shaped = _shape_match_details_from_cricbuzz(scorecard_data, commentary, miniscore, raw_comwrapper)

    # NEW: Epic 6 - attach venue/player insights alongside the existing
    # scorecard/commentary data. Purely additive - nothing above this line
    # changes behavior for existing frontend fields.
    _attach_intelligence(shaped, carousel_entry, miniscore)

    with _detail_cache_lock:
        _detail_cache[match_id] = {
            "data": shaped,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
            "cricbuzz_match_id": cricbuzz_match_id,
            "backfilled_innings": backfilled_innings,
        }


def _innings_total_overs(carousel_entry: dict | None) -> "int | None":
    fmt = (carousel_entry or {}).get("matchFormat", "").upper()
    if "TEST" in fmt:
        return None
    if "ODI" in fmt or "50" in fmt or "LIST A" in fmt:
        return 50
    return 20


def _is_death_overs(current_over_str: str, total_overs: "int | None") -> bool:
    if total_overs is None:
        return False
    try:
        current_over = float(current_over_str)
    except Exception:
        return False
    return current_over >= (total_overs - 5)


def _wicket_in_recent_ball_tracker(shaped_detail: dict | None) -> bool:
    tracker = (shaped_detail or {}).get("ballTracker", [])
    return any(b.get("type") == "wicket" for b in tracker)


HOT_INTERVAL_SECONDS = 60
WARM_INTERVAL_SECONDS = 300
COLD_INTERVAL_SECONDS = 1800


def _refresh_interval_for_match(carousel_entry: dict | None, detail_entry: dict | None) -> int:
    status = (carousel_entry or {}).get("status")
    if status is None:
        # NEW: carousel_entry missing doesn't necessarily mean the match ended — it
        # can happen from a single transient miss on the /matches/v1/live poll, or a
        # Cricbuzz match-state string we don't map cleanly. Previously this fell
        # through to COLD_INTERVAL_SECONDS (30 min), which could silently freeze a
        # genuinely live match's scorecard for half an hour on a single bad cycle —
        # exactly the "stuck on an old over" symptom. If we have recent detail data
        # showing the match was live, keep refreshing at WARM pace instead of
        # dropping straight to COLD on missing/ambiguous carousel data.
        shaped_prior = (detail_entry or {}).get("data")
        if shaped_prior and shaped_prior.get("liveScore"):
            return WARM_INTERVAL_SECONDS
        return COLD_INTERVAL_SECONDS
    if status != "LIVE":
        return COLD_INTERVAL_SECONDS
    shaped = (detail_entry or {}).get("data")
    live_score = (shaped or {}).get("liveScore") or {}
    current_overs = (
        (live_score.get("home") or {}).get("info")
        if shaped and not shaped.get("innings2")
        else (live_score.get("away") or {}).get("info")
    )
    hot = _is_death_overs(current_overs, _innings_total_overs(carousel_entry)) or _wicket_in_recent_ball_tracker(shaped)
    # Budget-aware: if we're already close to the daily cap, never use the hot tier —
    # fall back to warm so we don't burn through the remaining calls on one match.
    snap = _quota_snapshot()
    if hot and snap["remaining"] > 20:
        return HOT_INTERVAL_SECONDS
    return WARM_INTERVAL_SECONDS


def _background_loop() -> None:
    _refresh_live_matches()
    last_live_refresh = time.time()
    while True:
        time.sleep(5)
        now = time.time()

        with _cache_lock:
            has_live = any(m.get("status") == "LIVE" for m in _cache["live_and_recent"])
        live_list_interval = REFRESH_INTERVAL_SECONDS if has_live else NO_LIVE_BACKOFF_SECONDS

        if now - last_live_refresh >= live_list_interval:
            _refresh_live_matches()
            last_live_refresh = now

        with _cache_lock:
            carousel_by_id = {str(m.get("id")): m for m in _cache["live_and_recent"]}
        with _detail_cache_lock:
            snapshot = dict(_detail_cache)

        due_for_refresh = []
        for mid, entry in snapshot.items():
            interval = _refresh_interval_for_match(carousel_by_id.get(mid), entry)
            if now - datetime.fromisoformat(entry["last_refreshed"]).timestamp() >= interval:
                due_for_refresh.append(mid)

        for mid in due_for_refresh:
            if not _quota_has_budget():
                log.warning("Skipping scheduled refresh for match %s — quota exhausted", mid)
                with _detail_cache_lock:
                    if mid in _detail_cache:
                        # NEW: record that this match's refresh was blocked, and when,
                        # so /api/health and /api/match-details can surface it instead
                        # of a scorecard silently going stale with no visible cause.
                        _detail_cache[mid]["last_blocked_at"] = datetime.now(timezone.utc).isoformat()
                continue
            with _detail_cache_lock:
                if mid in _detail_cache:
                    _detail_cache[mid].pop("last_blocked_at", None)
            _refresh_match_detail(mid)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/api/live-scores", methods=["GET"])
def get_live_scores():
    with _cache_lock:
        return jsonify({
            "liveAndRecent": _cache["live_and_recent"],
            "lastRefreshed": _cache["last_refreshed"],
            "lastError": _cache["last_error"],
        })


@app.route("/api/match-details/<match_id>", methods=["GET"])
def get_match_details(match_id: str):
    with _detail_cache_lock:
        entry = _detail_cache.get(match_id)

    if entry is None:
        if not _quota_has_budget():
            # No cached detail and no budget left — tell the frontend honestly
            # instead of silently failing or burning the last calls on a cold view.
            return jsonify({"error": "Daily API quota exhausted. Try again after reset.", "quotaExhausted": True}), 503
        _refresh_match_detail(match_id)
        with _detail_cache_lock:
            entry = _detail_cache.get(match_id)

    if entry is None:
        return jsonify({"error": "Could not fetch match details"}), 502
    # NEW: expose lastRefreshed and whether the most recent scheduled refresh was
    # blocked by quota exhaustion, so staleness has a visible, diagnosable cause
    # instead of silently serving old data with no signal.
    return jsonify({
        **entry["data"],
        "lastRefreshed": entry["last_refreshed"],
        "refreshBlocked": "last_blocked_at" in entry,
        "lastBlockedAt": entry.get("last_blocked_at"),
    })


@app.route("/api/quota-status", methods=["GET"])
def quota_status():
    return jsonify(_quota_snapshot())


@app.route("/api/health", methods=["GET"])
def health():
    with _cache_lock:
        cache_snapshot = dict(_cache)
    return jsonify({
        "status": "ok",
        "hasCricketDataKey": bool(CRICKETDATA_API_KEY),
        "hasRapidApiKey": bool(RAPIDAPI_KEY),
        "intelligenceAvailable": _INTELLIGENCE_AVAILABLE,
        "refreshIntervalSeconds": REFRESH_INTERVAL_SECONDS,
        "quota": _quota_snapshot(),
        "cache": cache_snapshot,
    })


_bg_thread_lock = threading.Lock()
_bg_thread_started = False


def _ensure_background_thread_started() -> None:
    global _bg_thread_started
    if _bg_thread_started:
        return
    with _bg_thread_lock:
        if _bg_thread_started:
            return
        t = threading.Thread(target=_background_loop, daemon=True)
        t.start()
        _bg_thread_started = True


@app.before_request
def _start_background_on_first_request():
    _ensure_background_thread_started()


if __name__ == "__main__":
    _ensure_background_thread_started()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
