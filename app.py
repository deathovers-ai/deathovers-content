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
    from app_integration import build_live_state
    from match_intelligence_api import get_match_insights, determine_phase
    _INTELLIGENCE_AVAILABLE = True
    log.info("Intelligence Engine loaded successfully.")
except Exception as _intel_import_err:
    build_live_state = None
    get_match_insights = None
    determine_phase = None
    _INTELLIGENCE_AVAILABLE = False
    log.warning(
        "Intelligence Engine unavailable at startup (%s) - /api/match-details will "
        "omit the 'intelligence' key until this is resolved.", _intel_import_err
    )

# Weather (Open-Meteo, free, no key) - separate, independent import so a
# failure here never takes down the Intelligence Engine or the rest of
# the app. Coordinates come from Cricbuzz's own venueInfo, not a
# geocoding step - see weather_service.py docstring.
try:
    from weather_service import fetch_weather, compute_local_hour, check_dew_risk
    _WEATHER_AVAILABLE = True
except Exception as _weather_import_err:
    fetch_weather = None
    compute_local_hour = None
    check_dew_risk = None
    _WEATHER_AVAILABLE = False
    log.warning("Weather service unavailable at startup (%s) - weather chip will be omitted.", _weather_import_err)

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
# NEW: when the SITE ITSELF has had no visitors at all recently (regardless
# of whether a match is live somewhere), back off much further than either
# of the above - there's no point refreshing the carousel every 15 minutes
# for a site nobody's currently browsing.
SITE_IDLE_BACKOFF_SECONDS = int(os.environ.get("SITE_IDLE_BACKOFF_SECONDS", 3600))
REQUEST_TIMEOUT_SECONDS = 10

# RapidAPI BASIC daily cap for cricbuzz-cricket2 is often ~100, NOT 450.
# Keep a safety margin below the real plan limit. Override via env, e.g.
# RAPIDAPI_DAILY_CALL_CAP=90 if your RapidAPI dashboard shows 100/day.
RAPIDAPI_DAILY_CALL_CAP = int(os.environ.get("RAPIDAPI_DAILY_CALL_CAP", 90))

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
# Local call counts reset whenever Render restarts, but RapidAPI's real daily
# quota does NOT. So we also trip a provider-side breaker when RapidAPI returns
# "exceeded the DAILY quota" and refuse further calls until the UTC day rolls.

_quota_lock = threading.Lock()
_quota = {
    "calls_today": 0,
    "day_started": datetime.now(timezone.utc).date().isoformat(),
    "blocked_calls": 0,
    "provider_exhausted": False,
    "provider_message": None,
    "provider_exhausted_at": None,
}


def _quota_reset_if_new_day() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if _quota["day_started"] != today:
        _quota["day_started"] = today
        _quota["calls_today"] = 0
        _quota["blocked_calls"] = 0
        _quota["provider_exhausted"] = False
        _quota["provider_message"] = None
        _quota["provider_exhausted_at"] = None


def _quota_has_budget() -> bool:
    with _quota_lock:
        _quota_reset_if_new_day()
        if _quota["provider_exhausted"]:
            return False
        return _quota["calls_today"] < RAPIDAPI_DAILY_CALL_CAP


def _quota_consume() -> None:
    with _quota_lock:
        _quota_reset_if_new_day()
        _quota["calls_today"] += 1


def _quota_note_blocked() -> None:
    with _quota_lock:
        _quota_reset_if_new_day()
        _quota["blocked_calls"] += 1


def _quota_trip_provider(message: str) -> None:
    """RapidAPI told us the real daily quota is gone — stop all further calls today."""
    with _quota_lock:
        _quota_reset_if_new_day()
        _quota["provider_exhausted"] = True
        _quota["provider_message"] = (message or "")[:300]
        _quota["provider_exhausted_at"] = datetime.now(timezone.utc).isoformat()
        # Treat remaining local budget as spent so /api/quota-status is honest.
        _quota["calls_today"] = max(_quota["calls_today"], RAPIDAPI_DAILY_CALL_CAP)


def _quota_snapshot() -> dict:
    with _quota_lock:
        _quota_reset_if_new_day()
        remaining = 0 if _quota["provider_exhausted"] else max(0, RAPIDAPI_DAILY_CALL_CAP - _quota["calls_today"])
        return {
            "callsToday": _quota["calls_today"],
            "dailyCap": RAPIDAPI_DAILY_CALL_CAP,
            "remaining": remaining,
            "blockedCalls": _quota["blocked_calls"],
            "dayStarted": _quota["day_started"],
            "providerExhausted": _quota["provider_exhausted"],
            "providerMessage": _quota["provider_message"],
            "providerExhaustedAt": _quota["provider_exhausted_at"],
        }


def _is_rapidapi_quota_error(status_code: int | None, body_text: str) -> bool:
    text = (body_text or "").lower()
    if "exceeded the daily quota" in text or "exceeded the monthly quota" in text:
        return True
    if "quota" in text and ("exceed" in text or "limit" in text):
        return True
    if status_code in (429, 403) and "quota" in text:
        return True
    return False


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
        snap = _quota_snapshot()
        reason = "provider exhausted" if snap.get("providerExhausted") else f"local cap {RAPIDAPI_DAILY_CALL_CAP}"
        log.warning("RapidAPI budget blocked (%s) — skipping call to %s", reason, path)
        return None

    url = f"{CRICBUZZ_BASE}{path}"
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": CRICBUZZ_HOST}
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=REQUEST_TIMEOUT_SECONDS)
        _quota_consume()  # count the call whether it succeeds or fails — it still hit RapidAPI
        body_text = ""
        try:
            body_text = resp.text or ""
        except Exception:
            body_text = ""

        if _is_rapidapi_quota_error(resp.status_code, body_text):
            _quota_trip_provider(body_text.strip() or f"HTTP {resp.status_code} quota error")
            log.error("RapidAPI provider quota exhausted — tripping breaker. body=%s", body_text[:200])
            return None

        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        # Some RapidAPI error bodies still land here after raise_for_status.
        msg = str(e)
        if _is_rapidapi_quota_error(None, msg):
            _quota_trip_provider(msg)
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
    """Prefer /scard; fall back to /hscard when the primary endpoint returns
    nothing usable (confirmed gap for some completed matches where /comm is
    empty and /scard intermittently returns an empty body)."""
    data = _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/scard")
    if _scorecard_innings_list(data):
        return data
    alt = _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/hscard")
    if _scorecard_innings_list(alt):
        return alt
    return data or alt


def _scorecard_innings_list(scorecard_data: dict | None) -> list:
    """Cricbuzz has shipped both `scorecard` and `scoreCard` keys; tolerate both."""
    if not scorecard_data:
        return []
    return (
        scorecard_data.get("scorecard")
        or scorecard_data.get("scoreCard")
        or scorecard_data.get("scorecardList")
        or []
    )


def _innings_id_of(inn: dict) -> int | None:
    raw = inn.get("inningsid", inn.get("inningsId", inn.get("innings_id")))
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _format_dismissal(batter: dict) -> str:
    """Builds a human-readable dismissal line, e.g. 'c Kohli b Bumrah', 'b Starc',
    'run out (Warner/Smith)', 'lbw b Cummins', or 'not out'."""
    outdec = (batter.get("outdec") or batter.get("outDec") or "").strip()
    if not outdec or outdec.lower() in ("not out", "batting"):
        return "not out" if outdec.lower() != "batting" else "batting"
    return outdec


def _shape_innings_from_cricbuzz(inn: dict) -> dict:
    batting = inn.get("batsman") or inn.get("batsmen") or []
    bowling = inn.get("bowler") or inn.get("bowlers") or []
    team = inn.get("batteamname") or inn.get("batTeamName") or inn.get("batteamnm") or ""
    runs = inn.get("score", inn.get("runs"))
    wickets = inn.get("wickets", inn.get("wicket"))
    overs = inn.get("overs", inn.get("over"))
    return {
        "team": team,
        "score": f"{runs}/{wickets}" if runs is not None else "",
        "overs": str(overs if overs is not None else ""),
        "batters": [
            {
                "name": b.get("name", "Unknown"),
                "r": b.get("runs", b.get("r", 0)),
                "b": b.get("balls", b.get("b", 0)),
                "sr": str(b.get("strkrate", b.get("strikeRate", b.get("sr", "")))),
                # Mute yet-to-bat rows; keep dismissed + current batters readable.
                "dim": (
                    int(b.get("balls", b.get("b", 0)) or 0) == 0
                    and int(b.get("runs", b.get("r", 0)) or 0) == 0
                    and (b.get("outdec") or b.get("outDec") or "").strip().lower() in ("", "not out")
                ),
                "dismissal": _format_dismissal(b),
            }
            for b in batting
        ],
        "bowlers": [
            {
                "name": bo.get("name", "Unknown"),
                "o": str(bo.get("overs", bo.get("o", ""))),
                "r": str(bo.get("runs", bo.get("r", ""))),
                "w": str(bo.get("wickets", bo.get("w", ""))),
                "eco": str(bo.get("economy", bo.get("eco", ""))),
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


def _parse_toss_from_status(status_text: "str | None", team1_name: str, team2_name: str) -> "dict | None":
    """
    Cricbuzz's matchInfo.status field carries the toss announcement as a
    plain string ONLY while matchInfo.state == "Toss" - e.g. "Zimbabwe
    opt to bowl", "France opt to bat" (confirmed via real live data, 25
    Jul 2026). Once play starts, status is overwritten with a live-state
    description instead (e.g. "Sri Lanka Women need 117 runs") and no
    longer contains toss info - callers MUST capture this once while
    state is "Toss" and persist it (see _toss_archive below), not
    re-parse status on every poll.

    Returns {"winner": str, "decision": "bat"|"bowl"} or None if the
    string doesn't match the toss-announcement pattern.
    """
    if not status_text:
        return None
    m = re.match(r"^(.+?)\s+opt(?:ed)?\s+to\s+(bat|bowl)\b", status_text.strip(), re.IGNORECASE)
    if not m:
        return None
    winner_raw = m.group(1).strip()
    decision = m.group(2).lower()
    for name in (team1_name, team2_name):
        if name and winner_raw.lower() == name.lower():
            return {"winner": name, "decision": decision}
    return {"winner": winner_raw, "decision": decision}


# ---------------------------------------------------------------------------
# Toss archive - same "capture once, persist" pattern as
# _first_innings_archive, and the same reason: Cricbuzz's status field
# only carries the toss announcement transiently (see
# _parse_toss_from_status docstring above), so it must be captured the
# moment it's seen and cached for the rest of the match. In-memory only,
# same known restart-loses-history tradeoff as the first-innings archive.
# ---------------------------------------------------------------------------
_toss_archive_lock = threading.Lock()
_toss_archive: dict[str, dict] = {}


def _record_toss_if_new(match_id: str, toss: "dict | None") -> None:
    if not match_id or not toss:
        return
    with _toss_archive_lock:
        if match_id not in _toss_archive:
            _toss_archive[match_id] = toss


def _get_archived_toss(match_id: str) -> "dict | None":
    with _toss_archive_lock:
        return _toss_archive.get(match_id)


# ---------------------------------------------------------------------------
# Weather cache - fetched once pregame + once at innings break per match,
# not on every poll (weather doesn't change meaningfully within a single
# refresh cycle, and this keeps calls minimal even though Open-Meteo's
# free tier is generous). Keyed by match_id -> {"weather": {...}, "fetched_for_innings": int}.
# In-memory only, same lifetime/tradeoff as the other archives in this file.
# ---------------------------------------------------------------------------
_weather_cache_lock = threading.Lock()
_weather_cache: dict[str, dict] = {}


def _should_fetch_weather(match_id: str, current_innings_id: "int | None") -> bool:
    """True if we've never fetched weather for this match, OR the innings
    has changed since our last fetch (innings-break refresh point)."""
    if current_innings_id is None:
        return False
    with _weather_cache_lock:
        entry = _weather_cache.get(match_id)
    if entry is None:
        return True
    return entry.get("fetched_for_innings") != current_innings_id


def _refresh_weather_if_needed(match_id: str, carousel_entry: "dict | None",
                                current_innings_id: "int | None") -> "dict | None":
    """
    Fetches and caches weather for this match if due (see
    _should_fetch_weather). Returns the cached (possibly just-updated)
    weather dict, or None if weather is unavailable for any reason
    (service down, venue has no coordinates, fetch failed) - never
    raises, weather is purely additive.
    """
    if not _WEATHER_AVAILABLE or not carousel_entry:
        return None
    lat = carousel_entry.get("venueLatitude")
    lon = carousel_entry.get("venueLongitude")
    if lat is None or lon is None:
        return None

    if _should_fetch_weather(match_id, current_innings_id):
        weather = fetch_weather(lat, lon)
        if weather is not None:
            with _weather_cache_lock:
                _weather_cache[match_id] = {"weather": weather, "fetched_for_innings": current_innings_id}

    with _weather_cache_lock:
        entry = _weather_cache.get(match_id)
    return entry["weather"] if entry else None


def _shape_match_for_carousel(m: dict) -> dict:
    info = m.get("matchInfo", m)
    team1 = info.get("team1", {}) or {}
    team2 = info.get("team2", {}) or {}

    home_name = team1.get("teamName", team1.get("teamname", "TBD"))
    away_name = team2.get("teamName", team2.get("teamname", "TBD"))

    # Capture toss the moment we see it (state == "Toss"), before status
    # gets overwritten by live-play text on the next poll.
    match_id_for_toss = info.get("matchId", info.get("matchid"))
    if (info.get("state") or "").lower() == "toss":
        parsed_toss = _parse_toss_from_status(info.get("status"), home_name, away_name)
        if match_id_for_toss and parsed_toss:
            _record_toss_if_new(str(match_id_for_toss), parsed_toss)

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

    # NEW (weather): Cricbuzz's own venueInfo already includes latitude/
    # longitude/timezone directly - confirmed real from live carousel data,
    # no separate geocoding step needed. startDate (epoch ms) + venue
    # timezone together let us compute the match's local start hour for
    # dew-risk detection. All optional - venues without these fields
    # simply get no weather chip, never a guessed/wrong one.
    def _to_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    venue_lat = _to_float(venue.get("latitude"))
    venue_lon = _to_float(venue.get("longitude"))
    venue_timezone = venue.get("timezone")
    start_date_epoch_ms = info.get("startDate")

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
        # NEW: weather inputs (see comment above)
        "venueLatitude": venue_lat,
        "venueLongitude": venue_lon,
        "venueTimezone": venue_timezone,
        "startDateEpochMs": start_date_epoch_ms,
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
    scorecard_list = _scorecard_innings_list(scorecard_data)

    def _find_innings(innings_id: int) -> dict | None:
        for inn in scorecard_list:
            if _innings_id_of(inn) == innings_id:
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

    # If inningsid fields were missing/odd, still surface whatever scorecard rows
    # we got so completed matches don't render as a blank board.
    if not all_innings and scorecard_list:
        for idx, raw in enumerate(scorecard_list, start=1):
            shaped_inn = _shape_innings_from_cricbuzz(raw)
            shaped_inn["inningsId"] = _innings_id_of(raw) or idx
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

    # When miniscore is missing (common on completed matches and intermittent
    # live gaps), still build a header score from the scorecard innings so the
    # match page isn't blank above a fully populated batting card.
    if live_score is None and all_innings:
        def _fmt_from_inn(inn: dict | None) -> dict:
            if not inn or not inn.get("score"):
                return {"score": "yet to bat", "info": ""}
            return {"score": inn.get("score", "0/0"), "info": str(inn.get("overs") or "")}

        live_score = {
            "home": _fmt_from_inn(all_innings[0] if len(all_innings) >= 1 else None),
            "away": _fmt_from_inn(all_innings[1] if len(all_innings) >= 2 else None),
            "target": 0,
            "crr": 0,
            "rrr": 0,
            "lastWicket": "",
            "customStatus": "",
        }

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


# Max legal deliveries kept for situation detection (collapse/momentum/
# pressure windows only look back 24/18/12 balls respectively - 30 gives
# headroom without holding a whole innings in memory per match).
MAX_RECENT_BALLS = 30


def _runs_for_commentary_type(ctype: str, text: str) -> int:
    """Map a shaped commentary entry's `type` to a runs value. 'run' is the
    ambiguous one (covers 1/2/3/5) - text usually contains the digit as a
    leading token in Cricbuzz's commentary strings ('1 run', '2 runs').
    Falls back to 1 (a single) if no digit is found - reasonable default
    since ambiguous 'run' entries are overwhelmingly singles in real data,
    and the pointers this feeds (wicket/dot/boundary counts) aren't
    sensitive to a single-vs-double misclassification."""
    if ctype == "wicket":
        return 0
    if ctype == "six":
        return 6
    if ctype == "four":
        return 4
    if ctype == "dot":
        return 0
    m = re.match(r"^\s*(\d+)\s*run", text or "", re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 1


def _derive_recent_balls_from_commentary(commentary: list[dict], innings_id: int) -> list[dict]:
    """
    Builds the `recent_balls` list situation_insight() needs, from the
    commentary we're already fetching/merging for the frontend feed - no
    new Cricbuzz calls required. commentary is newest-first (see
    _merge_commentary's final sort); this returns OLDEST-FIRST, matching
    what situation_insight()'s window slicing (recent_balls[-24:] etc)
    expects. Filtered to one innings only, so collapse/momentum detection
    never mixes balls from two different innings. Each returned ball
    carries its source ballnbr too (situation_insight ignores unknown
    keys, so this is safe for that caller) - used by
    _derive_full_innings_balls_from_commentary below to identify exactly
    which balls are new since a previous phase-bucketing pass, since this
    function's own output is a sliding window and NOT safe to use for
    that purpose on its own.
    """
    this_innings = [c for c in commentary if c.get("innings", 1) == innings_id]
    recent = this_innings[:MAX_RECENT_BALLS]
    return [
        {
            "runs_total": _runs_for_commentary_type(c.get("type"), c.get("text", "")),
            "is_wicket": c.get("type") == "wicket",
            "ballnbr": c.get("ballnbr", 0),
        }
        for c in reversed(recent)
    ]


def _derive_full_innings_balls_from_commentary(commentary: list[dict], innings_id: int) -> list[dict]:
    """
    Unlike _derive_recent_balls_from_commentary (capped to the most recent
    MAX_RECENT_BALLS for situation detection), this returns EVERY legal
    ball we currently have commentary for in this innings, oldest-first,
    each tagged with ballnbr and an approximate over number (ballnbr-1)//6.
    Used specifically for phase-bucketing the first-innings archive, where
    we need ball-number identity to correctly skip balls we've already
    attributed on a prior poll - a sliding recent-balls window can't do
    that safely once an innings passes 30 balls.
    """
    this_innings = [c for c in commentary if c.get("innings", 1) == innings_id and c.get("ballnbr")]
    ordered = sorted(this_innings, key=lambda c: c["ballnbr"])
    return [
        {
            "ballnbr": c["ballnbr"],
            "over": (c["ballnbr"] - 1) // 6,
            "runs_total": _runs_for_commentary_type(c.get("type"), c.get("text", "")),
            "is_wicket": c.get("type") == "wicket",
        }
        for c in ordered
    ]


def _derive_partnership_from_commentary(commentary: list[dict], innings_id: int) -> tuple:
    """
    Walks commentary (newest-first) forward until the most recent wicket
    for this innings, summing runs/balls along the way - everything more
    recent than that wicket is the current, unbroken partnership. Returns
    (partnership_runs, partnership_balls, balls_since_new_batter).
    balls_since_new_batter is None if no wicket has fallen yet this innings
    (no "new batter settling in" state applies at the very start).
    """
    this_innings = [c for c in commentary if c.get("innings", 1) == innings_id]
    runs, balls = 0, 0
    for c in this_innings:
        if c.get("type") == "wicket":
            break
        runs += _runs_for_commentary_type(c.get("type"), c.get("text", ""))
        balls += 1
    balls_since_new_batter = balls if any(c.get("type") == "wicket" for c in this_innings) else None
    return runs, balls, balls_since_new_batter


# ---------------------------------------------------------------------------
# First-innings score archive (Epic 6 extension - 2nd innings triple
# comparison needs "what was innings-1's score at this same over mark",
# AND "what did innings-1 actually score in each phase" for a true
# phase-vs-phase comparison rather than only a venue-historical one).
#
# Keyed by match_id -> {
#     "points": [{"over": float, "runs": int}, ...],   # for same-over lookup
#     "phase_scores": {"powerplay": {"runs": int, "balls": int}, "middle": {...}, "death": {...}}
# }
# Appended/accumulated once per refresh while innings 1 is the live innings.
# Small (a few dozen points + 3 phase counters per match) and lives only in
# memory, same lifetime as _detail_cache - no persistence needed since this
# is only useful during the live match itself. Known limitation: lost on a
# mid-match Render restart (ephemeral process memory, no disk/DB backing
# this yet) - _lookup functions correctly return None in that case rather
# than guessing, same refuse-don't-guess posture as the rest of the
# Insight Engine.
# ---------------------------------------------------------------------------
_first_innings_archive_lock = threading.Lock()
_first_innings_archive: dict[str, dict] = {}

_EMPTY_PHASE_SCORES = {
    "powerplay": {"runs": 0, "balls": 0},
    "middle": {"runs": 0, "balls": 0},
    "death": {"runs": 0, "balls": 0},
}


def _record_first_innings_point(match_id: str, over_decimal: "float | None", runs: "int | None",
                                 match_type: "str | None" = None, full_innings_balls: "list | None" = None) -> None:
    """
    Records a same-over snapshot point (existing behavior, unchanged in
    effect) AND, when full_innings_balls + match_type are supplied,
    buckets each ball this call has visibility into that we haven't
    already attributed to a phase on a prior call. Identifies "new" balls
    by ballnbr (tracked via the archive's own "highest_ballnbr_attributed"
    counter) rather than list position, since commentary/recent_balls can
    be a sliding window - position-based dedup breaks once an innings
    passes that window size, ballnbr identity does not. match_type/
    full_innings_balls are optional so this stays backward compatible
    with any caller that only wants the same-over point recorded.
    """
    if over_decimal is None or runs is None:
        return
    with _first_innings_archive_lock:
        entry = _first_innings_archive.setdefault(
            match_id,
            {"points": [], "phase_scores": {k: dict(v) for k, v in _EMPTY_PHASE_SCORES.items()},
             "highest_ballnbr_attributed": 0},
        )
        points = entry["points"]
        # Avoid duplicate/out-of-order points from re-polling the same over.
        already_seen_this_over = bool(points) and points[-1]["over"] >= over_decimal
        if not already_seen_this_over:
            points.append({"over": over_decimal, "runs": runs})

        if match_type is not None and full_innings_balls:
            highest_seen = entry["highest_ballnbr_attributed"]
            new_balls = [b for b in full_innings_balls if b["ballnbr"] > highest_seen]
            for ball in new_balls:
                phase = determine_phase(ball["over"], match_type)
                entry["phase_scores"][phase]["runs"] += ball["runs_total"]
                entry["phase_scores"][phase]["balls"] += 1
            if new_balls:
                entry["highest_ballnbr_attributed"] = max(b["ballnbr"] for b in new_balls)


def _lookup_first_innings_score_at_over(match_id: str, over_decimal: float) -> "int | None":
    """Finds the closest recorded innings-1 point at or before over_decimal.
    Returns None if we never captured innings 1 for this match (e.g. the
    app was restarted mid-match, or this match was only ever viewed from
    innings 2 onward) - correctly refuses rather than guessing."""
    with _first_innings_archive_lock:
        entry = _first_innings_archive.get(match_id)
    points = entry["points"] if entry else []
    candidates = [p for p in points if p["over"] <= over_decimal]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p["over"])["runs"]


def _lookup_first_innings_phase_score(match_id: str, phase_name: str) -> "dict | None":
    """Returns {"runs": int, "balls": int} for the given phase of innings 1
    at this match, or None if we have no archive for this match at all, or
    zero balls recorded for that specific phase (innings-1 simply hasn't
    reached - or was never observed in - that phase, e.g. the app started
    watching mid-innings and missed the powerplay). Never fabricates a
    partial/estimated figure - same posture as every other guard in this
    codebase."""
    with _first_innings_archive_lock:
        entry = _first_innings_archive.get(match_id)
    if not entry:
        return None
    phase_data = entry["phase_scores"].get(phase_name)
    if not phase_data or phase_data["balls"] == 0:
        return None
    return dict(phase_data)


def _current_innings_id_for_intelligence(shaped: dict, effective_miniscore: dict | None) -> int | None:
    """Resolve which innings is active for commentary-derived insight fields.

    The previous `live_state.get("current_over_number") is not None and miniscore...`
    expression collapsed to False whenever overs weren't on live_state yet, which
    silently skipped situation insights for many live and completed matches.
    """
    mid = (effective_miniscore or {}).get("inningsid")
    try:
        if mid is not None:
            return int(mid)
    except (TypeError, ValueError):
        pass
    inn2 = shaped.get("innings2")
    inn1 = shaped.get("innings1")
    if inn2 and inn2.get("score") and inn2.get("score") != "yet to bat":
        return int(inn2.get("inningsId") or 2)
    if inn1 and inn1.get("score") and inn1.get("score") != "yet to bat":
        return int(inn1.get("inningsId") or 1)
    return None


def _parse_runs_wickets(score: str | None) -> tuple[int | None, int | None]:
    if not score or score == "yet to bat":
        return None, None
    m = re.match(r"(\d+)/(\d+)", str(score))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _top_batters(innings: dict | None, limit: int = 2) -> list[dict]:
    batters = list((innings or {}).get("batters") or [])
    scored = [b for b in batters if isinstance(b.get("r"), (int, float)) or str(b.get("r", "")).isdigit()]
    scored.sort(key=lambda b: int(b.get("r") or 0), reverse=True)
    return scored[:limit]


def _build_match_tactical_fallback(shaped: dict, carousel_entry: dict | None) -> list[dict]:
    """Venue-agnostic tactical reads so Match Room is never empty when we already
    have a scoreline. Complements (does not replace) venue/situation insights."""
    insights: list[dict] = []
    status = (carousel_entry or {}).get("status") or ""
    chase_note = (carousel_entry or {}).get("chaseNote") or (shaped.get("liveScore") or {}).get("customStatus") or ""
    match_format = ((carousel_entry or {}).get("matchFormat") or "T20").upper()
    inn1 = shaped.get("innings1")
    inn2 = shaped.get("innings2")
    live = shaped.get("liveScore") or {}

    # 1) Match state / result card — always useful for live + completed.
    if status == "COMPLETED" and chase_note:
        pointers = [{"label": "Result", "value": chase_note}]
        if inn1 and inn1.get("score"):
            pointers.append({"label": inn1.get("team") or "1st innings", "value": f"{inn1.get('score')} ({inn1.get('overs') or '-'} ov)"})
        if inn2 and inn2.get("score"):
            pointers.append({"label": inn2.get("team") or "2nd innings", "value": f"{inn2.get('score')} ({inn2.get('overs') or '-'} ov)"})
        insights.append({
            "type": "match_recap",
            "headline": "Match recap",
            "pointers": pointers,
        })
    elif chase_note or live.get("target") or live.get("crr") or live.get("rrr"):
        pointers = []
        if chase_note:
            pointers.append({"label": "Situation", "value": chase_note})
        if live.get("target"):
            pointers.append({"label": "Target", "value": live.get("target")})
        if live.get("crr"):
            pointers.append({"label": "CRR", "value": live.get("crr")})
        if live.get("rrr"):
            pointers.append({"label": "RRR", "value": live.get("rrr")})
        if pointers:
            insights.append({
                "type": "match_situation",
                "headline": "Live tactical snapshot",
                "pointers": pointers,
            })

    # 2) Phase read from current overs (format-aware, no venue required).
    active = inn2 if (inn2 and inn2.get("score") and inn2.get("score") != "yet to bat") else inn1
    if active and active.get("overs") not in (None, ""):
        try:
            overs_now = float(active.get("overs") or 0)
        except (TypeError, ValueError):
            overs_now = None
        runs, wickets = _parse_runs_wickets(active.get("score"))
        if overs_now is not None and runs is not None:
            if match_format in ("ODI", "ODM"):
                phase = "powerplay" if overs_now < 10 else ("middle" if overs_now < 40 else "death")
                total_ov = 50
            else:
                phase = "powerplay" if overs_now < 6 else ("middle" if overs_now < 15 else "death")
                total_ov = 20
            balls = int(overs_now) * 6 + int(round((overs_now % 1) * 10))
            crr = round((runs / balls) * 6, 2) if balls > 0 else None
            insights.append({
                "type": "phase_snapshot",
                "headline": f"{phase.title()} phase — {active.get('team') or 'batting side'}",
                "pointers": [
                    {"label": "Score", "value": f"{runs}/{wickets if wickets is not None else '-'}"},
                    {"label": "Overs", "value": overs_now},
                    *([{"label": "CRR", "value": crr}] if crr is not None else []),
                    {"label": "Phase", "value": f"{phase} (of {total_ov} ov)"},
                ],
            })

    # 3) Top-scorer card from the batting lists we already shaped.
    top_rows = []
    for inn, label in ((inn1, "1st innings"), (inn2, "2nd innings")):
        for b in _top_batters(inn, limit=1):
            if int(b.get("r") or 0) <= 0:
                continue
            top_rows.append({
                "label": f"{b.get('name')} ({label})",
                "value": f"{b.get('r')} ({b.get('b')}b, SR {b.get('sr') or '-'})",
            })
    if top_rows:
        insights.append({
            "type": "top_scorers",
            "headline": "Key batting performances",
            "pointers": top_rows,
        })

    return insights


def _merge_tactical_insights(primary: list, fallback: list) -> list:
    """Keep engine insights first; add fallback types that aren't already covered."""
    existing_types = {i.get("type") for i in primary if isinstance(i, dict)}
    # map related engine types so we don't duplicate the same story
    covered = set(existing_types)
    if "venue_pregame_summary" in existing_types:
        covered.add("match_recap")
    if any(t.startswith("situation_") or t in {"collapse", "pressure", "acceleration", "partnership"} for t in existing_types):
        covered.add("match_situation")
        covered.add("phase_snapshot")
    # also cover by headline-ish engine situation type names
    for t in list(existing_types):
        if t and "situation" in str(t):
            covered.add("match_situation")
            covered.add("phase_snapshot")

    merged = list(primary)
    for item in fallback:
        if item.get("type") in covered:
            continue
        # If engine already produced any venue/situation content, still allow
        # top_scorers + completed match_recap for even Match Room population.
        if primary and item.get("type") in {"match_situation", "phase_snapshot"} and (
            "venue_score_insight" in existing_types
            or any("situation" in str(t) for t in existing_types)
        ):
            continue
        merged.append(item)
        covered.add(item.get("type"))
    return merged


def _attach_intelligence(shaped: dict, carousel_entry: dict | None, miniscore: dict | None,
                          match_id: str = "", commentary: list | None = None) -> None:
    """
    Mutates `shaped` in place, adding an "intelligence" key with venue/player
    insights - or a clean empty/error shape if unavailable, so the frontend
    never has to special-case a missing key vs an empty insights list.
    Never raises - any failure here should degrade to no insights, not break
    the whole match-details response.

    Falls back to a synthetic miniscore built from shaped["innings1"/
    "innings2"] when the real miniscore is missing/empty - this is what
    fixes the confirmed real case where venue/format resolve correctly
    (Lord's, ODI, zero warnings) but insights still came back empty,
    because miniscore was None for that poll even though the score WAS
    actually available via the commentary-derived innings data.

    UPDATED (Epic 6 extension): also derives recent_balls/partnership from
    commentary (for situation_insight), current_over_decimal (for
    projection_insight), and first-innings-archive lookups + target/
    balls_remaining (for second_innings_comparison) - all optional, all
    silently skipped if the underlying data isn't available, same
    refuse-don't-guess posture as the rest of the Insight Engine. match_id/
    commentary are new optional params so existing callers/tests that don't
    pass them still work unchanged (defaults keep prior behavior exactly).

    UPDATED (even Match Room population): always merges venue-agnostic
    tactical fallback reads from the scorecard/chase line so live and
    completed matches still get Match Room content when the venue isn't in
    venue_stats.json or carousel lookup briefly misses.
    """
    fallback = _build_match_tactical_fallback(shaped, carousel_entry)

    if not _INTELLIGENCE_AVAILABLE:
        shaped["intelligence"] = {
            "insights": fallback,
            "meta": {"available": False, "fallback_used": bool(fallback)},
        }
        return

    if not carousel_entry:
        # Still attach fallback reads from the scorecard we do have, instead of
        # leaving Match Room completely empty on a multi-worker cache miss.
        shaped["intelligence"] = {
            "insights": fallback,
            "meta": {
                "available": True,
                "warnings": ["no carousel entry for this match"],
                "fallback_used": bool(fallback),
            },
        }
        return

    try:
        venue_name = carousel_entry.get("venue", "") or shaped.get("venue") or ""
        match_format = carousel_entry.get("matchFormat", "")
        series_name = carousel_entry.get("seriesName", "")
        is_ipl = "indian premier league" in (series_name + " " + venue_name).lower()

        # Keep venue on the shaped payload so Match Room / later refreshes
        # still have it even if carousel lookup briefly misses.
        if venue_name and not shaped.get("venue"):
            shaped["venue"] = venue_name

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

        live_state = build_live_state(venue_name, match_format, is_ipl, effective_miniscore)

        # --- Extend live_state with the new fields, all best-effort ---
        current_innings_id = _current_innings_id_for_intelligence(shaped, effective_miniscore)
        overs_completed_str = live_state.get("overs_completed_str")
        current_over_decimal = None
        if overs_completed_str is not None:
            try:
                current_over_decimal = float(overs_completed_str)
                live_state["current_over_decimal"] = current_over_decimal
            except (ValueError, TypeError):
                pass

        if commentary and current_innings_id:
            recent_balls = _derive_recent_balls_from_commentary(commentary, current_innings_id)
            if recent_balls:
                live_state["recent_balls"] = recent_balls
                live_state["legal_balls_bowled"] = int(round((current_over_decimal or 0) * 6)) \
                    if current_over_decimal is not None else None
            p_runs, p_balls, balls_since_new = _derive_partnership_from_commentary(commentary, current_innings_id)
            live_state["partnership_runs"] = p_runs
            live_state["partnership_balls"] = p_balls
            if balls_since_new is not None:
                live_state["balls_since_new_batter"] = balls_since_new

            # Chase math for situation/pressure detectors.
            target = (effective_miniscore or {}).get("target") or (shaped.get("liveScore") or {}).get("target")
            if not target and current_innings_id == 2:
                inn1_runs, _ = _parse_runs_wickets((shaped.get("innings1") or {}).get("score"))
                if inn1_runs is not None:
                    target = inn1_runs + 1
            if target and current_innings_id == 2:
                live_state["target"] = target
                rrr = (shaped.get("liveScore") or {}).get("rrr")
                if rrr:
                    live_state["required_run_rate"] = rrr

        if current_innings_id == 1 and match_id and current_over_decimal is not None \
                and "current_score" in live_state:
            full_innings_balls = (
                _derive_full_innings_balls_from_commentary(commentary, current_innings_id)
                if commentary else None
            )
            _record_first_innings_point(
                match_id, current_over_decimal, live_state["current_score"],
                match_type=match_format, full_innings_balls=full_innings_balls,
            )

        if current_innings_id == 2 and match_id:
            live_state["is_second_innings"] = True
            target = live_state.get("target") or (effective_miniscore or {}).get("target")
            if not target:
                inn1_runs, _ = _parse_runs_wickets((shaped.get("innings1") or {}).get("score"))
                if inn1_runs is not None:
                    target = inn1_runs + 1
            if target:
                live_state["target"] = target
                total_overs = 50 if match_format.upper() in ("ODI", "ODM") else 20
                legal_balls_bowled = live_state.get("legal_balls_bowled")
                if legal_balls_bowled is not None:
                    live_state["balls_remaining"] = max(0, total_overs * 6 - legal_balls_bowled)
            if current_over_decimal is not None:
                fi_score = _lookup_first_innings_score_at_over(match_id, current_over_decimal)
                if fi_score is not None:
                    live_state["first_innings_score_at_same_over"] = fi_score
                # Phase-wise 1st innings comparison: only meaningful if we
                # actually recorded innings-1 balls in that exact phase -
                # correctly stays unset (not guessed) otherwise.
                current_phase = determine_phase(int(current_over_decimal), match_format)
                fi_phase = _lookup_first_innings_phase_score(match_id, current_phase)
                if fi_phase is not None:
                    live_state["first_innings_phase_runs"] = fi_phase["runs"]
                    live_state["first_innings_phase_balls"] = fi_phase["balls"]

        result = get_match_insights(live_state)
        if used_fallback:
            result.setdefault("meta", {})["score_source"] = "commentary_fallback"

        engine_insights = result.get("insights") or []
        merged = _merge_tactical_insights(engine_insights, fallback)
        result["insights"] = merged
        result.setdefault("meta", {})["fallback_used"] = len(merged) > len(engine_insights)
        shaped["intelligence"] = result
    except Exception as e:
        log.error("Intelligence Engine failed for this match: %s", e)
        shaped["intelligence"] = {
            "insights": fallback,
            "meta": {"available": True, "error": str(e), "fallback_used": bool(fallback)},
        }


def _is_cricbuzz_match_id(match_id: str) -> bool:
    """CricketData fill matches use UUIDs; Cricbuzz IDs are numeric."""
    return str(match_id).isdigit()


def _detail_is_incomplete(shaped: dict | None) -> bool:
    """True when a refresh produced no real batting card or commentary —
    those should be retried on the next view instead of cached cold for 30 min."""
    if not shaped:
        return True
    inn1 = shaped.get("innings1") or {}
    has_batters = bool(inn1.get("batters"))
    has_commentary = bool(shaped.get("commentary"))
    return not has_batters and not has_commentary


def _innings_has_card(inn: dict | None) -> bool:
    return bool(inn and ((inn.get("batters") or inn.get("bowlers"))))


def _preserve_prior_scorecard(shaped: dict, prior_data: dict | None) -> dict:
    """Never let a flaky empty RapidAPI poll wipe a previously-good batting card.

    Confirmed regression: a live match had full batters/commentary, then one empty
    /scard+/comm cycle replaced it with carousel stubs and blanked the board.
    """
    if not prior_data:
        return shaped

    prior_innings = prior_data.get("innings") or []
    if not shaped.get("innings") and prior_innings:
        shaped["innings"] = prior_innings
    if not _innings_has_card(shaped.get("innings1")) and _innings_has_card(prior_data.get("innings1")):
        shaped["innings1"] = prior_data.get("innings1")
    if not _innings_has_card(shaped.get("innings2")) and _innings_has_card(prior_data.get("innings2")):
        shaped["innings2"] = prior_data.get("innings2")

    # Rebuild innings list aliases if we restored 1/2 but list was empty.
    if not shaped.get("innings") and (shaped.get("innings1") or shaped.get("innings2")):
        shaped["innings"] = [i for i in (shaped.get("innings1"), shaped.get("innings2")) if i]

    if not shaped.get("ballTracker") and prior_data.get("ballTracker"):
        shaped["ballTracker"] = prior_data.get("ballTracker")
    if not shaped.get("liveScore") and prior_data.get("liveScore"):
        shaped["liveScore"] = prior_data.get("liveScore")
    if not shaped.get("toss") and prior_data.get("toss"):
        shaped["toss"] = prior_data.get("toss")
    return shaped


def _shape_details_from_carousel(carousel_entry: dict | None, *, permanent: bool = True) -> dict:
    """Header-only fallback from the live carousel when full scorecard isn't available.

    For CricketData UUID matches (`permanent=True`) this is the best we can do.
    For flaky Cricbuzz polls (`permanent=False`) we only fill liveScore — we do
    NOT invent empty innings shells, which previously rendered as broken
    "batting card not loaded" columns on the match page.
    """
    score = (carousel_entry or {}).get("score") or {}
    teams = (carousel_entry or {}).get("teams") or []
    home = score.get("home")
    away = score.get("away")
    live_score = {
        "home": home or {"score": "yet to bat", "info": ""},
        "away": away or {"score": "yet to bat", "info": ""},
        "target": 0,
        "crr": 0,
        "rrr": 0,
        "lastWicket": "",
        "customStatus": (carousel_entry or {}).get("chaseNote") or "",
    }

    if not permanent:
        return {
            "toss": None,
            "venue": (carousel_entry or {}).get("venue") or "",
            "recentBalls": [],
            "commentary": [],
            "currentBowler": "",
            "innings": [],
            "innings1": None,
            "innings2": None,
            "liveScore": live_score,
            "ballTracker": [],
            "detailSource": "carousel_fallback",
            "detailNote": "Full scorecard is refreshing — showing live totals for now.",
        }

    innings = []
    if home and len(teams) >= 1:
        innings.append({
            "inningsId": 1,
            "team": teams[0],
            "score": home.get("score") or "",
            "overs": str(home.get("info") or ""),
            "batters": [],
            "bowlers": [],
        })
    if away and len(teams) >= 2:
        innings.append({
            "inningsId": 2,
            "team": teams[1],
            "score": away.get("score") or "",
            "overs": str(away.get("info") or ""),
            "batters": [],
            "bowlers": [],
        })
    return {
        "toss": None,
        "venue": (carousel_entry or {}).get("venue") or "",
        "recentBalls": [],
        "commentary": [],
        "currentBowler": "",
        "innings": innings,
        "innings1": innings[0] if len(innings) >= 1 else None,
        "innings2": innings[1] if len(innings) >= 2 else None,
        "liveScore": live_score,
        "ballTracker": [],
        "detailSource": "carousel_only",
        "detailNote": "Full ball-by-ball scorecard is not available for this match source yet.",
    }


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

    # CricketData UUID matches have no Cricbuzz scorecard/commentary endpoints.
    # Serve a carousel-backed stub instead of burning quota on guaranteed 404s.
    if not _is_cricbuzz_match_id(cricbuzz_match_id):
        shaped = _shape_details_from_carousel(carousel_entry, permanent=True)
        _attach_intelligence(shaped, carousel_entry, None, match_id=match_id, commentary=[])
        with _detail_cache_lock:
            _detail_cache[match_id] = {
                "data": shaped,
                "last_refreshed": datetime.now(timezone.utc).isoformat(),
                "cricbuzz_match_id": None,
                "backfilled_innings": set(),
                "incomplete": True,
            }
        return

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
    current_innings_id = 1
    if miniscore:
        innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])
        reported_innings_ids = [s.get("inningsid") for s in innings_scores if s.get("inningsid")]
        current_innings_id = max(reported_innings_ids) if reported_innings_ids else 1
    else:
        # Completed / miniscore-missing matches still need innings-2 commentary.
        # Infer from scorecard when possible; otherwise try innings 2 once.
        sc_list = _scorecard_innings_list(scorecard_data)
        sc_ids = [_innings_id_of(inn) for inn in sc_list]
        sc_ids = [i for i in sc_ids if i]
        if sc_ids:
            current_innings_id = max(sc_ids)
        elif (carousel_entry or {}).get("status") == "COMPLETED":
            current_innings_id = 2

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
    prior_data = (prior_entry or {}).get("data") if prior_entry else None
    prior_commentary = (prior_data or {}).get("commentary", []) if prior_data else []
    commentary = _merge_commentary(prior_commentary, commentary)

    shaped = _shape_match_details_from_cricbuzz(scorecard_data, commentary, miniscore, raw_comwrapper)
    shaped = _preserve_prior_scorecard(shaped, prior_data)

    # Toss result, if we've captured it for this match (see
    # _record_toss_if_new - captured once, while state=="Toss", from the
    # carousel entry). Falls back to parsing the SCORECARD endpoint's own
    # top-level "status" field, which - confirmed via a real live
    # scorecard response, match 155349 at over 29 - keeps the toss
    # announcement text ("Nepal opt to bowl") even well after toss,
    # unlike the live-matches feed's matchInfo.status which gets
    # overwritten by live-play text. This recovers toss for matches the
    # app started watching AFTER the "Toss" state had already passed
    # (the one real gap in the archive-only approach) - at zero extra
    # API cost, since scorecard_data is already being fetched every
    # refresh for the batting/bowling card.
    shaped["toss"] = _get_archived_toss(match_id) or shaped.get("toss")
    if shaped["toss"] is None and scorecard_data and carousel_entry:
        scorecard_status = scorecard_data.get("status")
        team1_name = carousel_entry["teams"][0] if carousel_entry.get("teams") else ""
        team2_name = carousel_entry["teams"][1] if len(carousel_entry.get("teams", [])) > 1 else ""
        fallback_toss = _parse_toss_from_status(scorecard_status, team1_name, team2_name)
        if fallback_toss:
            shaped["toss"] = fallback_toss
            _record_toss_if_new(match_id, fallback_toss)

    # If this poll still has no batting card/commentary, keep the HEADER scores
    # from the carousel — but do NOT invent empty innings columns. That was the
    # Match Room regression: live Cricbuzz matches rendered two blank
    # "batting card not loaded" panels plus a permanent-sounding note.
    if _detail_is_incomplete(shaped) and carousel_entry:
        fallback = _shape_details_from_carousel(carousel_entry, permanent=False)
        if not shaped.get("liveScore"):
            shaped["liveScore"] = fallback["liveScore"]
        else:
            shaped["liveScore"] = {
                **shaped["liveScore"],
                "home": (fallback["liveScore"].get("home") or shaped["liveScore"].get("home")),
                "away": (fallback["liveScore"].get("away") or shaped["liveScore"].get("away")),
                "customStatus": fallback["liveScore"].get("customStatus")
                    or shaped["liveScore"].get("customStatus"),
            }
        shaped["detailSource"] = "carousel_fallback"
        shaped["detailNote"] = fallback.get("detailNote")
    else:
        shaped.pop("detailNote", None)
        shaped.pop("detailSource", None)

    # Weather (Open-Meteo, free) - fetched once pregame + once per innings
    # change, using coordinates already present in the carousel entry's
    # venueInfo. Dew risk is computed alongside it since it needs the same
    # weather reading + the match's local start hour + current innings.
    #
    # BUGFIX: previously read current_innings_id directly off miniscore,
    # which is None on the confirmed-real intermittent Cricbuzz failure
    # mode (see ARCHITECTURE.md / _synthesize_miniscore_from_shaped_innings)
    # - meaning weather silently never fetched on exactly the polls where
    # the score itself was already correctly falling back to commentary-
    # derived data. Now uses the same fallback: prefer miniscore's own
    # inningsid when present, else derive it from whichever of
    # shaped["innings1"/"innings2"] actually has live data (mirrors
    # _synthesize_miniscore_from_shaped_innings's own "yet to bat" check).
    current_innings_id_for_weather = (miniscore or {}).get("inningsid")
    if current_innings_id_for_weather is None:
        inn2 = shaped.get("innings2")
        inn1 = shaped.get("innings1")
        if inn2 and inn2.get("score") and inn2["score"] != "yet to bat":
            current_innings_id_for_weather = inn2.get("inningsId", 2)
        elif inn1 and inn1.get("score") and inn1["score"] != "yet to bat":
            current_innings_id_for_weather = inn1.get("inningsId", 1)

    weather = _refresh_weather_if_needed(match_id, carousel_entry, current_innings_id_for_weather)
    shaped["weather"] = weather

    if weather and check_dew_risk and carousel_entry:
        local_hour = compute_local_hour(
            carousel_entry.get("startDateEpochMs"), carousel_entry.get("venueTimezone")
        )
        dew = check_dew_risk(
            is_second_innings=(current_innings_id_for_weather == 2),
            local_start_hour=local_hour,
            current_humidity_pct=weather.get("humidity_pct"),
        )
        shaped["dewRisk"] = dew
    else:
        shaped["dewRisk"] = None

    # Epic 6 - attach venue/player insights alongside the existing
    # scorecard/commentary data. Purely additive - nothing above this line
    # changes behavior for existing frontend fields. match_id/commentary
    # passed through so situation_insight/projection_insight/
    # second_innings_comparison have what they need (see _attach_intelligence
    # docstring for what each optional field unlocks).
    _attach_intelligence(shaped, carousel_entry, miniscore, match_id=match_id, commentary=commentary)

    incomplete = _detail_is_incomplete(shaped)
    with _detail_cache_lock:
        _detail_cache[match_id] = {
            "data": shaped,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
            "cricbuzz_match_id": cricbuzz_match_id,
            "backfilled_innings": backfilled_innings,
            "incomplete": incomplete,
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

        # NEW: three-tier interval instead of two - if the whole site has
        # had zero visitors recently, back off much further regardless of
        # whether a match happens to be live somewhere in the world. This
        # is the other half of the quota-waste fix: previously the
        # carousel kept refreshing at full speed as long as ANY match was
        # live anywhere, even with zero actual visitors to deathovers.com.
        if not _site_has_recent_activity():
            live_list_interval = SITE_IDLE_BACKOFF_SECONDS
        else:
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
            # NEW: the actual fix for quota being consumed with nobody
            # watching - a match only gets background-refreshed if someone
            # has requested it within the last VIEWER_ACTIVE_WINDOW_SECONDS.
            # Previously any match ever opened kept refreshing forever,
            # even minutes/hours after the last viewer closed the tab.
            if not _match_has_active_viewer(mid):
                continue
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

_site_activity_lock = threading.Lock()
# Updated by ANY API call (live-scores or match-details) - tracks whether
# the site has had ANY visitor recently at all, separate from per-match
# viewer tracking. Used to back off the carousel refresh hard when the
# whole site is idle (e.g. overnight, nobody's browsing at all) rather
# than just when there's no live match.
_last_site_activity = {"timestamp": 0.0}


def _mark_site_activity() -> None:
    with _site_activity_lock:
        _last_site_activity["timestamp"] = time.time()


def _site_has_recent_activity(window_seconds: int = 120) -> bool:
    with _site_activity_lock:
        last = _last_site_activity["timestamp"]
    return last > 0 and (time.time() - last) < window_seconds


@app.route("/api/live-scores", methods=["GET"])
def get_live_scores():
    _mark_site_activity()  # NEW: any hit to this route means someone's actually on the site
    with _cache_lock:
        return jsonify({
            "liveAndRecent": _cache["live_and_recent"],
            "lastRefreshed": _cache["last_refreshed"],
            "lastError": _cache["last_error"],
        })


_viewer_lock = threading.Lock()
# match_id -> timestamp of the most recent /api/match-details request for it.
# This is the actual fix for "quota burns even when nobody's watching" - the
# background loop previously kept refreshing every match ever opened,
# forever, regardless of whether anyone was still on that page. Now it only
# refreshes matches someone has requested within VIEWER_ACTIVE_WINDOW_SECONDS.
_last_viewed: dict[str, float] = {}

# Comfortably longer than the frontend's 20s detail-poll interval (see
# LiveCarousel.jsx's detailUpdater), so an actively-open match page never
# sees a gap - but short enough that closing the tab stops burning quota
# on that match within ~90s, not indefinitely.
VIEWER_ACTIVE_WINDOW_SECONDS = 90


def _mark_match_viewed(match_id: str) -> None:
    with _viewer_lock:
        _last_viewed[match_id] = time.time()


def _match_has_active_viewer(match_id: str) -> bool:
    with _viewer_lock:
        last = _last_viewed.get(match_id)
    return last is not None and (time.time() - last) < VIEWER_ACTIVE_WINDOW_SECONDS


INCOMPLETE_RETRY_SECONDS = 60


def _rehydrate_intelligence_if_empty(match_id: str, entry: dict) -> dict:
    """If a cached detail has batting/commentary but zero insights (pre-fallback
    cache, or a carousel miss on the original refresh), rebuild intelligence
    in-memory without spending RapidAPI quota."""
    data = entry.get("data") or {}
    insights = ((data.get("intelligence") or {}).get("insights")) or []
    if insights:
        return entry
    has_signal = bool(
        (data.get("innings1") or {}).get("batters")
        or data.get("commentary")
        or data.get("liveScore")
        or data.get("innings1")
    )
    if not has_signal:
        return entry

    with _cache_lock:
        carousel_entry = next(
            (m for m in _cache["live_and_recent"] if str(m.get("id")) == str(match_id)),
            None
        )
    shaped = dict(data)
    _attach_intelligence(
        shaped,
        carousel_entry,
        None,
        match_id=str(match_id),
        commentary=shaped.get("commentary") or [],
    )
    entry = {**entry, "data": shaped}
    with _detail_cache_lock:
        if match_id in _detail_cache:
            _detail_cache[match_id]["data"] = shaped
    return entry


@app.route("/api/match-details/<match_id>", methods=["GET"])
def get_match_details(match_id: str):
    _mark_match_viewed(match_id)  # NEW: records that someone is actually looking at this match right now
    _mark_site_activity()

    with _detail_cache_lock:
        entry = _detail_cache.get(match_id)

    should_refresh = entry is None
    if entry is not None and entry.get("incomplete") and _is_cricbuzz_match_id(match_id):
        try:
            age = time.time() - datetime.fromisoformat(entry["last_refreshed"]).timestamp()
        except Exception:
            age = INCOMPLETE_RETRY_SECONDS
        if age >= INCOMPLETE_RETRY_SECONDS:
            should_refresh = True

    if should_refresh:
        if not _quota_has_budget():
            # No cached detail and no budget left. Never expose quota/API internals
            # (provider messages, call counts) to customers on a live scoreboard.
            if entry is None:
                snap = _quota_snapshot()
                log.warning(
                    "Match detail cold-miss blocked for %s — quota exhausted (provider=%s)",
                    match_id,
                    bool(snap.get("providerExhausted")),
                )
                return jsonify({
                    "error": "Live scorecard temporarily unavailable. Please try again shortly.",
                    "quotaExhausted": True,
                }), 503
        else:
            _refresh_match_detail(match_id)
            with _detail_cache_lock:
                entry = _detail_cache.get(match_id)

    if entry is None:
        return jsonify({"error": "Could not fetch match details"}), 502

    entry = _rehydrate_intelligence_if_empty(match_id, entry)

    snap = _quota_snapshot()
    # NEW: expose lastRefreshed and whether the most recent scheduled refresh was
    # blocked by quota exhaustion, so staleness has a visible, diagnosable cause
    # instead of silently serving old data with no signal.
    return jsonify({
        **entry["data"],
        "lastRefreshed": entry["last_refreshed"],
        "refreshBlocked": "last_blocked_at" in entry or bool(snap.get("providerExhausted")),
        "lastBlockedAt": entry.get("last_blocked_at") or snap.get("providerExhaustedAt"),
        "detailIncomplete": bool(entry.get("incomplete")),
        "quotaExhausted": bool(snap.get("providerExhausted") or snap.get("remaining", 1) <= 0),
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
