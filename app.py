"""
app.py — DeathOvers live-data backend (v3)
"""

from __future__ import annotations

import os
import re
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
# Config
# ---------------------------------------------------------------------------

CRICKETDATA_API_KEY = os.environ.get("CRICKETDATA_API_KEY", "")
CRICKETDATA_BASE = "https://api.cricapi.com/v1"

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
CRICBUZZ_HOST = "cricbuzz-cricket2.p.rapidapi.com"
CRICBUZZ_BASE = f"https://{CRICBUZZ_HOST}"

CRICBUZZ_DETAIL_REFRESH_SECONDS = int(os.environ.get("CRICBUZZ_DETAIL_REFRESH_SECONDS", 1800))
REFRESH_INTERVAL_SECONDS = int(os.environ.get("REFRESH_INTERVAL_SECONDS", 900))
DETAIL_REFRESH_INTERVAL_SECONDS = int(os.environ.get("DETAIL_REFRESH_INTERVAL_SECONDS", 1800))
REQUEST_TIMEOUT_SECONDS = 10

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
# Fetch Helpers
# ---------------------------------------------------------------------------

def _cricketdata_get(path: str, params: dict) -> dict | None:
    if not CRICKETDATA_API_KEY: return None
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
    if not RAPIDAPI_KEY: return None
    url = f"{CRICBUZZ_BASE}{path}"
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": CRICBUZZ_HOST}
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("Cricbuzz request failed (%s): %s", path, e)
        return None

# ---------------------------------------------------------------------------
# Shapers & Parsers
# ---------------------------------------------------------------------------

def _resolve_commentary_placeholders(text: str, commentary_formats: list) -> str:
    if "$" not in text: return text
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

def _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id: str, innings_id: int = 1) -> dict:
    data = _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/comm", params={"iid": innings_id})
    if data is None: return {"commentary": [], "miniscore": None}
    
    entries = data.get("comwrapper", [])
    miniscore = data.get("miniscore")
    shaped = []
    
    for entry in entries:
        c = entry.get("commentary", {})
        raw_text = (c.get("commtxt") or "").strip()
        if not raw_text: continue
        text = _resolve_commentary_placeholders(raw_text, c.get("commentaryformats", []))
        if _is_system_announcement(text): continue

        event = (c.get("eventtype") or "NONE").upper()
        if "WICKET" in event: ctype = "wicket"
        elif "SIX" in event: ctype = "six"
        elif "FOUR" in event: ctype = "four"
        elif text.lower().startswith("no run"): ctype = "dot"
        else: ctype = "run"

        over_label = ""
        ballnbr = c.get("ballnbr", 0)
        overnum = c.get("overnum", 0)
        if isinstance(overnum, (int, float)) and overnum: over_label = f"{overnum:.1f}"
        elif isinstance(ballnbr, (int, float)) and ballnbr: over_label = f"{(ballnbr - 1) // 6}.{(ballnbr - 1) % 6 + 1}"

        shaped.append({
            "over": over_label,
            "type": ctype,
            "text": text,
            "ballnbr": ballnbr if isinstance(ballnbr, (int, float)) else 0,
            "timestamp": c.get("timestamp", 0),
        })
    return {"commentary": shaped[:30], "miniscore": miniscore}

def _fetch_cricbuzz_scorecard(cricbuzz_match_id: str) -> dict | None:
    return _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/scard")

def _shape_innings_from_cricbuzz(inn: dict) -> dict:
    batting = inn.get("batsman", [])
    bowling = inn.get("bowler", [])
    return {
        "team": inn.get("batteamname", ""),
        "score": f"{inn.get('score', '')}/{inn.get('wickets', '')}" if inn.get("score") is not None else "",
        "overs": str(inn.get("overs", "")),
        "batters": [{"name": b.get("name", "Unknown"), "r": b.get("runs", 0), "b": b.get("balls", 0), "sr": str(b.get("strkrate", "")), "dim": b.get("outdec", "").lower() == "not out"} for b in batting],
        "bowlers": [{"name": bo.get("name", "Unknown"), "o": str(bo.get("overs", "")), "r": str(bo.get("runs", "")), "w": str(bo.get("wickets", "")), "eco": str(bo.get("economy", ""))} for bo in bowling],
    }

def _extract_ball_tracker(miniscore: dict | None) -> list[dict]:
    """Parses the current over directly from Cricbuzz's overseplist.oversummary"""
    if not miniscore: return []
    oversep_list = miniscore.get("overseplist", {}).get("oversep", [])
    if not oversep_list: return []
    latest_over = oversep_list[0].get("oversummary", "").strip()
    if not latest_over: return []

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
    if state in ("in progress", "innings break", "toss", "stumps"): status = "LIVE"
    elif state in ("complete", "abandoned", "no result"): status = "COMPLETED"
    else: status = "UPCOMING"

    def _fmt(score: dict | None) -> "dict | None":
        if not score: return None
        return {"score": f"{score.get('runs', score.get('r', 0))}/{score.get('wickets', score.get('w', 0))}", "info": f"{score.get('overs', score.get('o', 0))}"}

    match_score = info.get("matchScore") or {}
    home_score = (match_score.get("team1Score") or {}).get("inngs1")
    away_score = (match_score.get("team2Score") or {}).get("inngs1")

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
    }

def _shape_match_details_from_cricbuzz(scorecard_data: dict | None, commentary: list[dict], miniscore: dict | None) -> dict:
    scorecard_list = (scorecard_data or {}).get("scorecard", [])
    def _find_innings(innings_id: int) -> dict | None:
        for inn in scorecard_list:
            if inn.get("inningsid") == innings_id: return inn
        return None

    inn1_raw = _find_innings(1)
    inn2_raw = _find_innings(2)
    innings1 = _shape_innings_from_cricbuzz(inn1_raw) if inn1_raw else None
    innings2 = _shape_innings_from_cricbuzz(inn2_raw) if inn2_raw else None

    toss_line = ""
    live_score = None
    if miniscore:
        innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])
        def _find_score(innings_id: int) -> dict | None:
            for s in innings_scores:
                if s.get("inningsid") == innings_id: return s
            return None

        s1 = _find_score(1)
        s2 = _find_score(2)

        def _overwrite_score(innings: dict | None, s: dict | None) -> None:
            if innings is not None and s is not None:
                innings["score"] = f"{s.get('runs', 0)}/{s.get('wickets', 0)}"
                innings["overs"] = str(s.get("overs", ""))

        _overwrite_score(innings1, s1)
        _overwrite_score(innings2, s2)

        def _fmt_live(s: dict | None) -> dict:
            if not s: return {"score": "yet to bat", "info": ""}
            return {"score": f"{s.get('runs', 0)}/{s.get('wickets', 0)}", "info": str(s.get("overs", ""))}

        # Added target, crr, rrr, and customStatus mappings here
        live_score = {
            "home": _fmt_live(s1),
            "away": _fmt_live(s2),
            "target": miniscore.get("target", 0),
            "crr": miniscore.get("crr", 0),
            "rrr": miniscore.get("rrr", 0),
            "lastWicket": miniscore.get("lastwkt", ""),
            "customStatus": miniscore.get("custstatus", "")
        }
        toss_line = miniscore.get("lastwkt", "")

    ball_tracker = _extract_ball_tracker(miniscore)

    return {
        "toss": toss_line,
        "venue": "",
        "recentBalls": [],
        "commentary": commentary,
        "currentBowler": "",
        "innings1": innings1,
        "innings2": innings2,
        "liveScore": live_score,
        "ballTracker": ball_tracker,
    }

def _shape_fill_match_from_cricketdata(m: dict) -> dict:
    teams = m.get("teams") or []
    home_name = teams[0] if len(teams) > 0 else "TBD"
    away_name = teams[1] if len(teams) > 1 else "TBD"
    raw_format = (m.get("matchType") or "").strip()
    return {
        "id": m.get("id"),
        "venue": m.get("venue", ""),
        "status": "COMPLETED" if m.get("matchEnded") else "UPCOMING",
        "matchName": m.get("name", f"{home_name} vs {away_name}"),
        "matchFormat": raw_format.upper() if raw_format else "UNKNOWN",
        "score": {"home": None, "away": None},
        "chaseNote": m.get("status", ""),
        "teams": [home_name, away_name],
        "homeImageId": crest_image_id(home_name),
        "awayImageId": crest_image_id(away_name),
    }

def _iter_cricbuzz_matches(list_payload: dict | None):
    if not list_payload: return
    for type_block in list_payload.get("typeMatches", []):
        for series in type_block.get("seriesMatches", []):
            wrapper = series.get("seriesAdWrapper", {})
            for match in wrapper.get("matches", []):
                info = match.get("matchInfo", {})
                if "matchScore" in match: info = {**info, "matchScore": match["matchScore"]}
                if info: yield info

def _refresh_live_matches() -> None:
    live_data = _cricbuzz_get("/matches/v1/live")
    live_shaped = [_shape_match_for_carousel(info) for info in _iter_cricbuzz_matches(live_data)]
    live_ids_by_teams = {tuple(sorted(m["teams"])) for m in live_shaped}

    cricketdata_data = _cricketdata_get("currentMatches", {"offset": 0})
    fill_shaped = []
    if cricketdata_data is not None:
        for m in cricketdata_data.get("data", []):
            teams = m.get("teams") or []
            if len(teams) < 2: continue
            if m.get("matchStarted") and not m.get("matchEnded"): continue
            if tuple(sorted(teams[:2])) in live_ids_by_teams: continue
            fill_shaped.append(_shape_fill_match_from_cricketdata(m))

    shaped = live_shaped + fill_shaped

    if live_data is None and cricketdata_data is None:
        with _cache_lock: _cache["last_error"] = f"refresh failed at {datetime.now(timezone.utc).isoformat()}"
        return

    with _cache_lock:
        _cache["live_and_recent"] = shaped
        _cache["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        _cache["last_error"] = None

def _refresh_match_detail(match_id: str) -> None:
    cricbuzz_match_id = str(match_id)
    if not cricbuzz_match_id: return
    comm_result = _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id, innings_id=1)
    commentary = comm_result["commentary"]
    miniscore = comm_result["miniscore"]
    scorecard_data = _fetch_cricbuzz_scorecard(cricbuzz_match_id)

    if miniscore:
        innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])
        if any(s.get("inningsid") == 2 for s in innings_scores):
            comm_result_2 = _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id, innings_id=2)
            if comm_result_2["commentary"]:
                commentary = comm_result_2["commentary"]
                miniscore = comm_result_2["miniscore"] or miniscore

    shaped = _shape_match_details_from_cricbuzz(scorecard_data, commentary, miniscore)
    with _detail_cache_lock:
        _detail_cache[match_id] = {
            "data": shaped,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
            "cricbuzz_match_id": cricbuzz_match_id,
        }

def _innings_total_overs(carousel_entry: dict | None) -> "int | None":
    fmt = (carousel_entry or {}).get("matchFormat", "").upper()
    if "TEST" in fmt: return None
    if "ODI" in fmt or "50" in fmt or "LIST A" in fmt: return 50
    return 20

def _is_death_overs(current_over_str: str, total_overs: "int | None") -> bool:
    if total_overs is None: return False
    try: current_over = float(current_over_str)
    except: return False
    return current_over >= (total_overs - 5)

def _wicket_in_recent_ball_tracker(shaped_detail: dict | None) -> bool:
    tracker = (shaped_detail or {}).get("ballTracker", [])
    return any(b.get("type") == "wicket" for b in tracker)

FREE_TIER_MODE = os.environ.get("FREE_TIER_MODE", "true").lower() == "true"
HOT_INTERVAL_SECONDS = 45
WARM_INTERVAL_SECONDS = 300
COLD_INTERVAL_SECONDS = 1800
HOT_TIER_DAILY_CALL_CAP = 40

def _refresh_interval_for_match(match_id: str, carousel_entry: dict | None, detail_entry: dict | None) -> int:
    status = (carousel_entry or {}).get("status")
    if status != "LIVE": return COLD_INTERVAL_SECONDS
    shaped = (detail_entry or {}).get("data")
    live_score = (shaped or {}).get("liveScore") or {}
    current_overs = (live_score.get("home") or {}).get("info") if shaped and not shaped.get("innings2") else (live_score.get("away") or {}).get("info")
    hot = _is_death_overs(current_overs, _innings_total_overs(carousel_entry)) or _wicket_in_recent_ball_tracker(shaped)
    if hot:
        if FREE_TIER_MODE and (detail_entry or {}).get("calls_today", 0) >= HOT_TIER_DAILY_CALL_CAP: return WARM_INTERVAL_SECONDS
        return HOT_INTERVAL_SECONDS
    return WARM_INTERVAL_SECONDS

def _background_loop() -> None:
    _refresh_live_matches()
    last_live_refresh = time.time()
    last_call_count_reset = time.time()
    while True:
        time.sleep(5)
        now = time.time()
        if now - last_live_refresh >= REFRESH_INTERVAL_SECONDS:
            _refresh_live_matches()
            last_live_refresh = now
        if now - last_call_count_reset >= 86400:
            with _detail_cache_lock:
                for entry in _detail_cache.values(): entry["calls_today"] = 0
            last_call_count_reset = now

        with _cache_lock: carousel_by_id = {str(m.get("id")): m for m in _cache["live_and_recent"]}
        with _detail_cache_lock: snapshot = dict(_detail_cache)

        due_for_refresh = []
        for mid, entry in snapshot.items():
            interval = _refresh_interval_for_match(mid, carousel_by_id.get(mid), entry)
            if now - datetime.fromisoformat(entry["last_refreshed"]).timestamp() >= interval:
                due_for_refresh.append(mid)

        for mid in due_for_refresh:
            _refresh_match_detail(mid)
            with _detail_cache_lock:
                if mid in _detail_cache:
                    _detail_cache[mid]["calls_today"] = _detail_cache[mid].get("calls_today", 0) + 1

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/api/live-scores", methods=["GET"])
def get_live_scores():
    with _cache_lock:
        return jsonify({"liveAndRecent": _cache["live_and_recent"], "lastRefreshed": _cache["last_refreshed"], "lastError": _cache["last_error"]})

@app.route("/api/match-details/<match_id>", methods=["GET"])
def get_match_details(match_id: str):
    with _detail_cache_lock: entry = _detail_cache.get(match_id)
    if entry is None:
        _refresh_match_detail(match_id)
        with _detail_cache_lock: entry = _detail_cache.get(match_id)
    if entry is None: return jsonify({"error": "Could not fetch match details"}), 502
    return jsonify(entry["data"])

@app.route("/api/health", methods=["GET"])
def health():
    with _cache_lock: cache_snapshot = dict(_cache)
    return jsonify({"status": "ok", "hasCricketDataKey": bool(CRICKETDATA_API_KEY), "hasRapidApiKey": bool(RAPIDAPI_KEY), "refreshIntervalSeconds": REFRESH_INTERVAL_SECONDS, "detailRefreshIntervalSeconds": DETAIL_REFRESH_INTERVAL_SECONDS, "cache": cache_snapshot})

_bg_thread_lock = threading.Lock()
_bg_thread_started = False

def _ensure_background_thread_started() -> None:
    global _bg_thread_started
    if _bg_thread_started: return
    with _bg_thread_lock:
        if _bg_thread_started: return
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
