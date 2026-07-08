"""
app.py — DeathOvers live-data backend (v2)

Replaces the old hardcoded LIVE_MATCH_DB mock with a real data source:
CricketData.org (api.cricapi.com), free tier.

WHY CACHING IS NOT OPTIONAL HERE:
CricketData.org's free tier allows only 100 requests/day, total, across
your whole account. LiveCarousel.jsx polls this backend every 30 seconds
per visitor. If we called CricketData.org directly on every request, a
SINGLE visitor sitting on the page for 1 hour would burn 120 calls  —
more than your entire day's quota — and the site would start failing for
everyone else within the first hour of any real traffic.

So this backend NEVER calls CricketData.org directly inside a request
handler. Instead:
  - A background loop refreshes an in-memory cache on a fixed interval.
  - All incoming HTTP requests (from n8n or the frontend) are served
    straight from that cache, at zero API cost.
  - You control your total daily spend with two numbers:
    REFRESH_INTERVAL_SECONDS and DETAIL_REFRESH_INTERVAL_SECONDS below.

BUDGET MATH (free tier = 100 calls/day):
  - currentMatches poll: 1 call every REFRESH_INTERVAL_SECONDS
    at 600s (10 min) -> 144 calls/day just for this alone, which is
    ALREADY over budget. So default is set to 900s (15 min) -> 96/day,
    leaving only ~4 calls/day of headroom for match_info detail calls.
  - match_info (per-match detail) is much heavier data and is only
    fetched for whichever match is *currently open* in a user's detail
    view, and only refreshed every DETAIL_REFRESH_INTERVAL_SECONDS.
    This is deliberately conservative. If you upgrade off the free tier,
    lower both intervals for a snappier feel.

If you want truer "live" updates, the fix is a paid CricketData.org tier
or a second free-tier account used as fallback — NOT lowering these
numbers carelessly, since that will get your key rate-limited or your
account throttled by CricketData.org itself.
"""

from __future__ import annotations

import os
import threading
import time
import logging
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify
from flask_cors import CORS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("deathovers-backend")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CRICKETDATA_API_KEY = os.environ.get("CRICKETDATA_API_KEY", "")
CRICKETDATA_BASE = "https://api.cricapi.com/v1"

# See budget math in the module docstring before changing these.
REFRESH_INTERVAL_SECONDS = int(os.environ.get("REFRESH_INTERVAL_SECONDS", 900))       # 15 min
DETAIL_REFRESH_INTERVAL_SECONDS = int(os.environ.get("DETAIL_REFRESH_INTERVAL_SECONDS", 1800))  # 30 min
REQUEST_TIMEOUT_SECONDS = 10

if not CRICKETDATA_API_KEY:
    log.warning(
        "CRICKETDATA_API_KEY is not set. The backend will run but every "
        "refresh cycle will fail and the API will keep serving the last "
        "known cache (empty on first boot). Set this env var on Render."
    )

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ---------------------------------------------------------------------------
# In-memory cache. Single-process assumption (fine for Render free tier /
# one gunicorn worker). If you ever scale to multiple workers/processes,
# this needs to move to something shared (Redis, etc) or each worker will
# maintain its own cache and independently burn API quota.
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache = {
    "live_and_recent": [],      # shaped for LiveCarousel's `matches` state
    "last_refreshed": None,     # ISO timestamp, for debugging/staleness checks
    "last_error": None,
}

# match_details cache is keyed by match id, each entry independently timestamped
_detail_cache_lock = threading.Lock()
_detail_cache: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# CricketData.org fetch helpers — these are the ONLY functions in this file
# allowed to call out to the real API. Everything else reads the cache.
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
        if data.get("status") != "success":
            log.error("CricketData.org returned non-success status: %s", data.get("status"))
            return None
        return data
    except requests.RequestException as e:
        log.error("CricketData.org request failed (%s): %s", path, e)
        return None
    except ValueError:
        log.error("CricketData.org returned non-JSON response for %s", path)
        return None


def _shape_match_for_carousel(m: dict) -> dict:
    """
    Map a single entry from GET /currentMatches into the shape
    LiveCarousel.jsx expects for its `matches` array:
        { id, venue, status, matchName, score: {home, away}, chaseNote }

    NOTE on a bug that was here before and is now fixed: the original version
    matched each score entry to a team purely by string-prefix on the
    `inning` field (e.g. does "India Women U19 Inning 1" start with
    "India Women U19"). That is fragile — CricketData.org's `inning` label
    formatting is not perfectly consistent across match types (domestic
    T20 leagues, internationals, tours all format slightly differently),
    so real matches were silently coming back with a correct home score
    and an incorrectly-empty "yet to bat" away score even when both teams
    had clearly batted (confirmed against live data on 2026-07-08).

    Fix: CricketData.org's `score` array is returned in innings-batted
    order, not team-labelled order. For a standard (non-Test) match with
    two teams, the simplest reliable mapping is positional: distinct
    innings entries, in order, alternate/accumulate per team as the
    innings actually happened. Since limited-overs matches normally have
    at most one innings per team, we now match by TEAM NAME CONTAINMENT
    in either direction (team_name in inning_label OR inning_label's team
    portion in team_name) rather than a strict prefix, which is far more
    tolerant of minor formatting differences, and — as a final fallback —
    we assign remaining unmatched score entries positionally in the order
    they appear if name-matching still comes up empty. This trades a small
    amount of theoretical precision (extremely rare ambiguous team-name
    overlaps) for actually working on the real data we observed.
    """
    score_list = m.get("score") or []
    teams = m.get("teams") or []
    home_name = teams[0] if len(teams) > 0 else "TBD"
    away_name = teams[1] if len(teams) > 1 else "TBD"

    def _matches_team(inning_label: str, team_name: str) -> bool:
        inning_label = inning_label.strip()
        team_name = team_name.strip()
        if not inning_label or not team_name:
            return False
        return (
            inning_label.startswith(team_name)
            or team_name.startswith(inning_label.split(" Inning")[0].strip())
            or team_name in inning_label
        )

    def _find_latest_score_for(team_name: str) -> dict | None:
        matches_for_team = [s for s in score_list if _matches_team(s.get("inning", ""), team_name)]
        return matches_for_team[-1] if matches_for_team else None

    home_score = _find_latest_score_for(home_name)
    away_score = _find_latest_score_for(away_name)

    # Positional fallback: if name-matching found neither (or only one) and
    # there are exactly as many score entries as teams, just assign by
    # order rather than showing an incorrect "yet to bat".
    if home_score is None and away_score is None and len(score_list) >= 1:
        home_score = score_list[0] if len(score_list) > 0 else None
        away_score = score_list[1] if len(score_list) > 1 else None
    elif home_score is None and len(score_list) >= 1:
        # away matched something -> home is likely the OTHER entry
        remaining = [s for s in score_list if s is not away_score]
        home_score = remaining[0] if remaining else None
    elif away_score is None and len(score_list) >= 2:
        remaining = [s for s in score_list if s is not home_score]
        away_score = remaining[0] if remaining else None

    def _fmt(score: dict | None) -> dict:
        if not score:
            return {"score": "yet to bat", "info": ""}
        r = score.get("r", 0)
        w = score.get("w", 0)
        o = score.get("o", 0)
        return {"score": f"{r}/{w}", "info": f"{o}"}

    return {
        "id": m.get("id"),
        "venue": m.get("venue", ""),
        "status": "LIVE" if m.get("matchStarted") and not m.get("matchEnded") else
                   ("COMPLETED" if m.get("matchEnded") else "UPCOMING"),
        "matchName": m.get("name", f"{home_name} vs {away_name}"),
        "score": {
            "home": _fmt(home_score),
            "away": _fmt(away_score),
        },
        "chaseNote": m.get("status", ""),  # cricapi's free-text status line,
                                            # e.g. "Team A need 26 runs in 16 balls"
    }


def _refresh_live_matches() -> None:
    data = _cricketdata_get("currentMatches", {"offset": 0})
    if data is None:
        with _cache_lock:
            _cache["last_error"] = f"refresh failed at {datetime.now(timezone.utc).isoformat()}"
        log.warning("Live match refresh failed; serving stale cache (if any).")
        return

    raw_matches = data.get("data", [])
    shaped = [_shape_match_for_carousel(m) for m in raw_matches]

    with _cache_lock:
        _cache["live_and_recent"] = shaped
        _cache["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        _cache["last_error"] = None

    log.info("Refreshed live matches: %d matches cached.", len(shaped))


def _shape_match_details(match_id: str, data: dict) -> dict:
    """
    Map GET /match_info?id=... into the shape LiveCarousel.jsx expects
    for a single match drilldown:
        { toss, venue, recentBalls, currentBowler, innings1, innings2, commentary }

    NOTE: CricketData.org's free tier match_info endpoint does NOT include
    ball-by-ball commentary text (that's a paid-tier feature on most
    cricket data providers, this one included, as far as the public docs
    show). So `recentBalls` and `commentary` will come back EMPTY on the
    free tier — this is a real data gap, not a bug. See the note in the
    project overview doc. Everything else (toss, venue, innings, batting/
    bowling figures) IS available on the free tier and is mapped below.
    """
    d = data.get("data", {})
    innings_list = d.get("scorecard", [])  # list of innings, cricapi shape

    def _shape_innings(inn: dict) -> dict:
        batting = inn.get("batting", [])
        bowling = inn.get("bowling", [])
        return {
            "team": inn.get("inning", "").split(" Inning")[0],
            "score": f"{inn.get('r', '')}/{inn.get('w', '')}" if inn.get("r") is not None else "",
            "overs": str(inn.get("o", "")),
            "batters": [
                {
                    "name": b.get("batsman", {}).get("name", "Unknown"),
                    "r": b.get("r", 0),
                    "b": b.get("b", 0),
                    "sr": str(b.get("sr", "")),
                }
                for b in batting
            ],
            "bowlers": [
                {
                    "name": bo.get("bowler", {}).get("name", "Unknown"),
                    "o": str(bo.get("o", "")),
                    "r": str(bo.get("r", "")),
                    "w": str(bo.get("w", "")),
                    "eco": str(bo.get("eco", "")),
                }
                for bo in bowling
            ],
        }

    innings1 = _shape_innings(innings_list[0]) if len(innings_list) > 0 else {}
    innings2 = _shape_innings(innings_list[1]) if len(innings_list) > 1 else {}

    return {
        "toss": d.get("tossWinner", "") and f"{d.get('tossWinner')} won, elected to {d.get('tossChoice', '')}",
        "venue": d.get("venue", ""),
        # Not available on CricketData.org free tier — see docstring above.
        "recentBalls": [],
        "commentary": [],
        "currentBowler": "",  # not reliably present on free tier match_info
        "innings1": innings1,
        "innings2": innings2,
    }


def _refresh_match_detail(match_id: str) -> None:
    data = _cricketdata_get("match_info", {"id": match_id})
    if data is None:
        log.warning("Match detail refresh failed for %s; serving stale cache (if any).", match_id)
        return

    shaped = _shape_match_details(match_id, data)
    with _detail_cache_lock:
        _detail_cache[match_id] = {
            "data": shaped,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
        }
    log.info("Refreshed match detail for %s", match_id)


# ---------------------------------------------------------------------------
# Background refresh loop
# ---------------------------------------------------------------------------

def _background_loop() -> None:
    # Immediate first refresh on boot so the API isn't empty on first request.
    _refresh_live_matches()

    last_live_refresh = time.time()
    while True:
        time.sleep(5)
        now = time.time()

        if now - last_live_refresh >= REFRESH_INTERVAL_SECONDS:
            _refresh_live_matches()
            last_live_refresh = now

        # Refresh any match detail that's been requested at least once and
        # is due for a refresh. We only refresh details someone actually
        # asked for (see /api/match-details/<id> below), never all of them —
        # that would burn quota on matches nobody is even viewing.
        with _detail_cache_lock:
            due_for_refresh = [
                mid for mid, entry in _detail_cache.items()
                if now - _parse_iso(entry["last_refreshed"]) >= DETAIL_REFRESH_INTERVAL_SECONDS
            ]
        for mid in due_for_refresh:
            _refresh_match_detail(mid)


def _parse_iso(ts: str) -> float:
    return datetime.fromisoformat(ts).timestamp()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/api/live-scores", methods=["GET"])
def get_live_scores():
    """
    Consumed by LiveCarousel.jsx (carousel view) AND by the n8n pipeline.
    Always served from cache — zero API cost per request.
    """
    with _cache_lock:
        return jsonify({
            "liveAndRecent": _cache["live_and_recent"],
            "lastRefreshed": _cache["last_refreshed"],
            "lastError": _cache["last_error"],
        })


@app.route("/api/match-details/<match_id>", methods=["GET"])
def get_match_details(match_id: str):
    """
    Consumed by LiveCarousel.jsx when a user taps into a specific match.
    First request for a given match_id triggers an immediate fetch (so the
    user isn't staring at nothing); subsequent requests are served from
    cache until the background loop refreshes it again.
    """
    with _detail_cache_lock:
        entry = _detail_cache.get(match_id)

    if entry is None:
        # Not cached yet — fetch synchronously just this once. This is the
        # ONE place a request handler can cause an API call, and it only
        # happens the first time a specific match is opened by anyone.
        _refresh_match_detail(match_id)
        with _detail_cache_lock:
            entry = _detail_cache.get(match_id)

    if entry is None:
        return jsonify({"error": "Could not fetch match details"}), 502

    return jsonify(entry["data"])


@app.route("/api/health", methods=["GET"])
def health():
    """Simple uptime/debug endpoint — not used by the frontend."""
    with _cache_lock:
        cache_snapshot = dict(_cache)
    return jsonify({
        "status": "ok",
        "hasApiKey": bool(CRICKETDATA_API_KEY),
        "refreshIntervalSeconds": REFRESH_INTERVAL_SECONDS,
        "detailRefreshIntervalSeconds": DETAIL_REFRESH_INTERVAL_SECONDS,
        "cache": cache_snapshot,
    })


# ---------------------------------------------------------------------------
# Boot
#
# IMPORTANT — why the background thread starts here and not at module import
# time: gunicorn's default sync worker model imports this module once in the
# MASTER process (to validate the app callable), then FORKS worker
# processes. A thread started during that master-process import does NOT
# survive into the forked worker — the worker gets a fresh, empty in-memory
# state, including _cache, and never runs the thread that would fill it.
# The master's background thread happily refreshes a _cache dict that no
# HTTP request will ever read, while the worker serving real traffic has an
# eternally empty one. This was the actual bug: 25 matches got cached in the
# master process, zero requests ever saw them.
#
# Fix: start the background thread lazily, from inside a request handler,
# the first time this worker process actually serves a request. A
# threading.Lock + flag ensures it only starts once per worker even under
# concurrent first requests.
# ---------------------------------------------------------------------------

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
        log.info("Background refresh thread started in worker pid=%s", os.getpid())


@app.before_request
def _start_background_on_first_request():
    _ensure_background_thread_started()


if __name__ == "__main__":
    # Local/dev run (not gunicorn) — start immediately since there's no fork.
    _ensure_background_thread_started()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
