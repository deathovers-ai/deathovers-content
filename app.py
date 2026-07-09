"""
app.py — DeathOvers live-data backend (v3)

CricketData.org (api.cricapi.com) is used ONLY for the live-matches
CAROUSEL list (GET /currentMatches) — that's cheap, list-shaped data and
CricketData's free tier handles it fine.

Cricbuzz Cricket2 (RapidAPI) is now the SINGLE SOURCE OF TRUTH for
everything in the match-DETAIL view once a user opens a specific match:
score, innings/batting/bowling tables, AND ball-by-ball commentary.

WHY THIS CHANGED (v2 -> v3): the detail view used to mix CricketData's
match_info (for the scoreboard) with Cricbuzz's commentary -- two
different providers on two different refresh cadences. That produced a
real, confirmed bug (2026-07-09 screenshot): scoreboard showed 169/6
(42 overs) while commentary was already at ball 42.3 with a six that
should have changed the score. Two providers can never be guaranteed to
agree on a "current" instant. The fix is to stop needing them to agree:
use Cricbuzz for BOTH numbers, from ONE API response, so they are
guaranteed to be the same snapshot.

Cricbuzz's commentary endpoint (/mcenter/v1/{id}/comm) was confirmed
(2026-07-09, real sample) to return a `miniscore` block alongside the
comwrapper commentary list, containing the live score
(miniscore.inningsscores.inningsscore[]), current batters/bowlers, run
rates, and last-wicket info -- all from the exact same fetch as the
commentary feed. That block is now the scoreboard's source, not
CricketData.

CricketData.org is STILL used to discover which real-world matches exist
right now (the carousel list) and to seed team names for Cricbuzz
name-resolution -- that part is unchanged from v2.

WHY CACHING IS NOT OPTIONAL HERE:
CricketData.org's free tier allows only 100 requests/day, total, across
your whole account. LiveCarousel.jsx polls this backend every 30 seconds
per visitor. If we called CricketData.org directly on every request, a
SINGLE visitor sitting on the page for 1 hour would burn 120 calls --
more than your entire day's quota -- and the site would start failing
for everyone else within the first hour of any real traffic.

Cricbuzz Cricket2 on RapidAPI has its OWN separate 100/day limit
(confirmed on the Basic/free plan, 2026-07-09).

So this backend NEVER calls either provider directly inside a request
handler except the very first time a given match detail is opened (see
get_match_details). Instead:
  - A background loop refreshes an in-memory cache on a fixed interval.
  - All incoming HTTP requests (from n8n or the frontend) are served
    straight from that cache, at zero API cost.
  - You control your total daily spend with the interval constants below.

BUDGET MATH (each free tier = 100 calls/day):
  - currentMatches poll (CricketData): 1 call every REFRESH_INTERVAL_SECONDS.
    at 900s (15 min) -> 96/day.
  - match detail refresh (Cricbuzz commentary+miniscore, ONE call covers
    both score and commentary now instead of two separate provider
    calls): 1 call every DETAIL_REFRESH_INTERVAL_SECONDS per open match,
    plus one extra Cricbuzz call per match the FIRST time it's opened
    (to resolve the Cricbuzz numeric match id via the live-list endpoint).
    At 1800s (30 min), each actively-viewed match costs ~48 calls/day on
    its own -- so realistically only 1-2 matches can be "hot" at a time
    on the free tier. If you upgrade off free tier, lower the interval.
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("deathovers-backend")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CRICKETDATA_API_KEY = os.environ.get("CRICKETDATA_API_KEY", "")
CRICKETDATA_BASE = "https://api.cricapi.com/v1"

# Cricbuzz Cricket2 on RapidAPI -- now the ONLY source for match-detail
# score + commentary. CricketData's match_info is no longer used for the
# detail view at all (still used for the carousel list -- see
# _refresh_live_matches). Cricbuzz uses its own numeric match IDs that do
# NOT correspond to CricketData.org's UUID-style match IDs -- there is no
# shared key between the two providers for the same real-world match. See
# _resolve_cricbuzz_match_id() for how that gap is bridged (team-name
# matching against Cricbuzz's own live-match list).
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
CRICBUZZ_HOST = "cricbuzz-cricket2.p.rapidapi.com"
CRICBUZZ_BASE = f"https://{CRICBUZZ_HOST}"

# Also a 100/day hard limit (confirmed on RapidAPI's Basic/free plan for
# this API, 2026-07-09) -- a SEPARATE budget from CricketData.org's 100/day,
# since these are different providers. Same discipline applies: never call
# from inside a request handler, only from the background refresh loop,
# and only for matches someone has actually opened.
CRICBUZZ_DETAIL_REFRESH_SECONDS = int(os.environ.get("CRICBUZZ_DETAIL_REFRESH_SECONDS", 1800))  # 30 min

# See budget math in the module docstring before changing these.
REFRESH_INTERVAL_SECONDS = int(os.environ.get("REFRESH_INTERVAL_SECONDS", 900))       # 15 min
DETAIL_REFRESH_INTERVAL_SECONDS = int(os.environ.get("DETAIL_REFRESH_INTERVAL_SECONDS", 1800))  # 30 min
REQUEST_TIMEOUT_SECONDS = 10

if not CRICKETDATA_API_KEY:
    log.warning(
        "CRICKETDATA_API_KEY is not set. The carousel list will stay "
        "empty. Set this env var on Render."
    )

if not RAPIDAPI_KEY:
    log.warning(
        "RAPIDAPI_KEY is not set. Match detail pages will not work at all "
        "-- score, innings, and commentary all now come from Cricbuzz "
        "Cricket2 on RapidAPI. Set this env var on Render."
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

# match_details cache is keyed by the CricketData match id (what the
# frontend already knows/uses from the carousel), each entry independently
# timestamped. The resolved Cricbuzz numeric id is cached alongside it so
# repeat refreshes never re-spend a resolution call.
_detail_cache_lock = threading.Lock()
_detail_cache: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# CricketData.org fetch helper -- used ONLY for the carousel list now.
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


def _cricbuzz_get(path: str, params: dict | None = None) -> dict | None:
    """
    Shared fetch helper for the Cricbuzz Cricket2 RapidAPI. Same pattern as
    _cricketdata_get: never called from inside a request handler except
    the one documented exception in get_match_details, so real usage stays
    inside the 100/day free-tier budget.
    """
    if not RAPIDAPI_KEY:
        return None
    url = f"{CRICBUZZ_BASE}{path}"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": CRICBUZZ_HOST,
    }
    try:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.error("Cricbuzz request failed (%s): %s", path, e)
        return None
    except ValueError:
        log.error("Cricbuzz returned non-JSON response for %s", path)
        return None


def _normalize_team_name(name: str) -> str:
    """Lowercase + strip common noise words so team names from two
    different providers can be compared for a match."""
    return " ".join(name.lower().replace("-", " ").split())


def _resolve_cricbuzz_match_id(team1_name: str, team2_name: str) -> str | None:
    """
    Bridge the gap between CricketData.org's UUID match IDs and Cricbuzz's
    numeric match IDs -- there is no shared identifier between the two
    providers for the same real-world match, confirmed 2026-07-09. This
    fetches Cricbuzz's own live-match list and finds the entry whose two
    team names both appear (in either order) among our target names.

    Path confirmed correct 2026-07-09: "/matches/v1/live" (NOT
    "/mcenter/v1/matches/live" -- that guessed path 404'd; "mcenter" is
    only for match-center calls that take a specific matchId, which the
    live list is not).
    """
    data = _cricbuzz_get("/matches/v1/live")
    if data is None:
        return None

    target1 = _normalize_team_name(team1_name)
    target2 = _normalize_team_name(team2_name)

    try:
        for type_block in data.get("typeMatches", []):
            for series in type_block.get("seriesMatches", []):
                wrapper = series.get("seriesAdWrapper", {})
                for match in wrapper.get("matches", []):
                    info = match.get("matchInfo", {})
                    t1 = _normalize_team_name(info.get("team1", {}).get("teamName", ""))
                    t2 = _normalize_team_name(info.get("team2", {}).get("teamName", ""))
                    names_here = {t1, t2}
                    if {target1, target2} == names_here or (target1 in names_here and target2 in names_here):
                        return str(info.get("matchId"))
    except (KeyError, TypeError) as e:
        log.warning("Unexpected shape from Cricbuzz live-matches while resolving id: %s", e)

    return None


def _resolve_commentary_placeholders(text: str, commentary_formats: list) -> str:
    """
    Replace Cricbuzz's literal "B0$", "B1$", etc. placeholder tokens in
    commtxt with the actual bold text they refer to, pulled from the
    matching commentaryformats entry.
    """
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

    dismissal_lead_pattern = r".*?(?:caught by [^!]*!!|run out!!|bowled!!|stumped!!)\s*"
    cleaned = re.sub(dismissal_lead_pattern, "", result, flags=re.IGNORECASE)
    if cleaned and cleaned != result:
        result = cleaned.strip()
    else:
        result = re.sub(r"^(.*?),\s*out\s+", r"\1, ", result, count=1, flags=re.IGNORECASE)

    return result


def _is_system_announcement(text: str) -> bool:
    """
    Filter out Cricbuzz's short duplicate/system rows that carry no new
    information beyond the real commentary row for the same ball.
    """
    t = text.strip().lower()
    system_phrases = ("thats out!!", "caught!!", "bowled!!", "run out!!", "stumped!!")
    if any(phrase in t for phrase in system_phrases) and len(t) < 60:
        return True
    if "comes to the crease" in t:
        return True
    if "is back into the attack" in t or "into the attack" in t:
        return True
    if "time for drinks" in t:
        return True
    return False


def _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id: str, innings_id: int = 1) -> dict:
    """
    Fetch ball-by-ball commentary AND the live miniscore in ONE Cricbuzz
    call -- this is the fix for the score/commentary sync bug (2026-07-09
    screenshot: scoreboard showed 169/6 (42) while commentary was already
    at ball 42.3 with a six that should have changed the score). That bug
    existed because the scoreboard and commentary used to come from two
    different providers on two different refresh cadences. Now both come
    from this single response, so they can never disagree.

    Confirmed real shape (2026-07-09 sample, IND vs BAN T20I):
        comwrapper: [ {commentary: {commtxt, timestamp, overnum, ballnbr,
                                     inningsid, eventtype, commentaryformats,
                                     batteamscore}}, ... ]
        miniscore: {
            batsmanstriker, batsmannonstriker,
            bowlerstriker, bowlernonstriker,
            crr, rrr,
            lastwkt,
            inningsscores: { inningsscore: [
                { inningsid, batteamid, batteamshortname, runs, wickets,
                  overs, target, balls }, ...
            ]},
            partnership, curovsstats, ...
        }

    CONFIRMED QUIRKS (do not "fix" these differently without re-checking
    a real payload first):
      - `overnum` on every commentary row in the sample was 0. NOT a
        reliable per-ball over number, despite being named that way.
      - `ballnbr` was also 0 on the sample rows given. If it stays 0 for
        in-play matches too, over/ball display should fall back to
        miniscore's own over count rather than inventing a number.
      - `batteamscore` on each commentary row was 0 in every sample row
        given -- NOT used as a per-ball running score. The live score
        comes from `miniscore.inningsscores` instead, which IS populated
        correctly in the sample (132/3 in 11.5 overs, matching the
        scorecard's own numbers).
    """
    data = _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/comm", params={"iid": innings_id})
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
        })

    return {"commentary": shaped[:30], "miniscore": miniscore}


def _fetch_cricbuzz_scorecard(cricbuzz_match_id: str) -> dict | None:
    """
    Fetch the full scorecard (both innings' batting/bowling tables) from
    Cricbuzz. Confirmed real shape (2026-07-09 sample):
        scorecard: [ { inningsid, score, wickets, overs, batteamname,
                        batsman: [{name, runs, balls, fours, sixes,
                                   strkrate, outdec}, ...],
                        bowler: [{name, overs, runs, wickets, economy}, ...]
                      }, ... ]
        status, ismatchcomplete
    """
    return _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/scard")


def _shape_innings_from_cricbuzz(inn: dict) -> dict:
    """
    Map one entry of Cricbuzz's scorecard[] into the shape
    LiveCarousel.jsx's InningsPanel expects.
    """
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
                "dim": b.get("outdec", "").lower() == "not out",
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


def _extract_ball_tracker(commentary: list[dict]) -> list[dict]:
    """
    Build the "current over" ball tracker from the commentary feed -- a
    compact strip of the balls bowled in the over currently in progress
    (resets each over, per product decision 2026-07-09).
    """
    balls = []
    current_over_int = None

    for row in commentary:
        over = row.get("over", "")
        if not over:
            continue

        try:
            over_int = int(float(over.lstrip("~")))
        except ValueError:
            continue

        if current_over_int is None:
            current_over_int = over_int
        elif over_int != current_over_int:
            break

        ctype = row.get("type", "run")
        text = row.get("text", "")
        if ctype == "wicket":
            label = "W"
        elif ctype == "six":
            label = "6"
        elif ctype == "four":
            label = "4"
        elif ctype == "dot":
            label = "\u2022"
        else:
            m = re.search(r"\b([1-5])\s*run", text.lower())
            label = m.group(1) if m else "\u2022"

        balls.append({"label": label, "type": ctype})

    balls.reverse()
    return balls


def _shape_match_for_carousel(m: dict) -> dict:
    """
    Map a single entry from GET /currentMatches (CricketData.org) into the
    shape LiveCarousel.jsx expects for its `matches` array. UNCHANGED from
    v2 and still uses CricketData -- only the match-DETAIL view has moved
    to Cricbuzz exclusively.
    """
    score_list = m.get("score") or []
    teams = m.get("teams") or []
    home_name = teams[0] if len(teams) > 0 else "TBD"
    away_name = teams[1] if len(teams) > 1 else "TBD"

    first_innings_score = score_list[0] if len(score_list) > 0 else None
    second_innings_score = score_list[1] if len(score_list) > 1 else None

    def _fmt(score: dict | None) -> dict:
        if not score:
            return {"score": "yet to bat", "info": ""}
        r = score.get("r", 0)
        w = score.get("w", 0)
        o = score.get("o", 0)
        return {"score": f"{r}/{w}", "info": f"{o}"}

    home_score = first_innings_score
    away_score = second_innings_score

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
        "chaseNote": m.get("status", ""),
        "teams": [home_name, away_name],
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


def _shape_match_details_from_cricbuzz(scorecard_data: dict | None, commentary: list[dict],
                                         miniscore: dict | None) -> dict:
    """
    Build the full shape LiveCarousel.jsx expects for a match drilldown,
    entirely from Cricbuzz data now.

    `liveScore` is NEW (v3): the miniscore-derived score object the
    frontend should now trust over any positional/derived score, since
    it's guaranteed same-snapshot as `commentary`.

    `ballTracker` is NEW (v3): the current-over ball-by-ball strip.
    """
    scorecard_list = (scorecard_data or {}).get("scorecard", [])

    def _find_innings(innings_id: int) -> dict | None:
        for inn in scorecard_list:
            if inn.get("inningsid") == innings_id:
                return inn
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
                if s.get("inningsid") == innings_id:
                    return s
            return None

        s1 = _find_score(1)
        s2 = _find_score(2)

        def _fmt_live(s: dict | None) -> dict:
            if not s:
                return {"score": "yet to bat", "info": ""}
            return {
                "score": f"{s.get('runs', 0)}/{s.get('wickets', 0)}",
                "info": str(s.get("overs", "")),
            }

        live_score = {
            "home": _fmt_live(s1),
            "away": _fmt_live(s2),
            "target": (s1 or s2 or {}).get("target", 0),
            "crr": miniscore.get("crr", 0),
            "rrr": miniscore.get("rrr", 0),
            "lastWicket": miniscore.get("lastwkt", ""),
        }
        toss_line = miniscore.get("lastwkt", "")

    ball_tracker = _extract_ball_tracker(commentary)

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


def _refresh_match_detail(match_id: str) -> None:
    """
    Refresh one match's detail entry. `match_id` is the CricketData id the
    frontend already knows (from the carousel).
    """
    with _detail_cache_lock:
        existing_entry = _detail_cache.get(match_id)
        cached_cricbuzz_id = existing_entry.get("cricbuzz_match_id") if existing_entry else None

    with _cache_lock:
        carousel_entry = next((m for m in _cache["live_and_recent"] if str(m.get("id")) == str(match_id)), None)

    cricbuzz_match_id = cached_cricbuzz_id
    if cricbuzz_match_id is None and RAPIDAPI_KEY and carousel_entry:
        teams = carousel_entry.get("teams", [])
        if len(teams) >= 2 and teams[0] != "TBD" and teams[1] != "TBD":
            cricbuzz_match_id = _resolve_cricbuzz_match_id(teams[0], teams[1])
            if cricbuzz_match_id:
                log.info("Resolved Cricbuzz match id %s for %s vs %s", cricbuzz_match_id, teams[0], teams[1])
            else:
                log.info("Could not resolve a Cricbuzz match id for %s vs %s (detail view will stay empty)", teams[0], teams[1])

    if not cricbuzz_match_id:
        log.warning("No Cricbuzz match id available for %s; cannot refresh detail.", match_id)
        return

    comm_result = _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id, innings_id=1)
    commentary = comm_result["commentary"]
    miniscore = comm_result["miniscore"]

    if miniscore:
        innings_scores = (miniscore.get("inningsscores") or {}).get("inningsscore", [])
        has_innings2 = any(s.get("inningsid") == 2 for s in innings_scores)
        if has_innings2:
            comm_result_2 = _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id, innings_id=2)
            if comm_result_2["commentary"]:
                commentary = comm_result_2["commentary"]
                miniscore = comm_result_2["miniscore"] or miniscore

    scorecard_data = _fetch_cricbuzz_scorecard(cricbuzz_match_id)

    shaped = _shape_match_details_from_cricbuzz(scorecard_data, commentary, miniscore)
    with _detail_cache_lock:
        _detail_cache[match_id] = {
            "data": shaped,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
            "cricbuzz_match_id": cricbuzz_match_id,
        }
    log.info("Refreshed match detail for %s via Cricbuzz (commentary rows: %d)", match_id, len(commentary))


# ---------------------------------------------------------------------------
# Background refresh loop
# ---------------------------------------------------------------------------

def _background_loop() -> None:
    _refresh_live_matches()

    last_live_refresh = time.time()
    while True:
        time.sleep(5)
        now = time.time()

        if now - last_live_refresh >= REFRESH_INTERVAL_SECONDS:
            _refresh_live_matches()
            last_live_refresh = now

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
        _refresh_match_detail(match_id)
        with _detail_cache_lock:
            entry = _detail_cache.get(match_id)

    if entry is None:
        return jsonify({"error": "Could not fetch match details"}), 502

    return jsonify(entry["data"])


@app.route("/api/health", methods=["GET"])
def health():
    with _cache_lock:
        cache_snapshot = dict(_cache)
    return jsonify({
        "status": "ok",
        "hasCricketDataKey": bool(CRICKETDATA_API_KEY),
        "hasRapidApiKey": bool(RAPIDAPI_KEY),
        "refreshIntervalSeconds": REFRESH_INTERVAL_SECONDS,
        "detailRefreshIntervalSeconds": DETAIL_REFRESH_INTERVAL_SECONDS,
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
        log.info("Background refresh thread started in worker pid=%s", os.getpid())


@app.before_request
def _start_background_on_first_request():
    _ensure_background_thread_started()


if __name__ == "__main__":
    _ensure_background_thread_started()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
