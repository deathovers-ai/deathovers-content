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

# Second data source, used ONLY for match-detail drilldowns (toss, full
# scorecard, and — the reason this was added — ball-by-ball commentary,
# which CricketData.org's free tier does not provide at all. Cricbuzz uses
# its own numeric match IDs that do NOT correspond to CricketData.org's
# UUID-style match IDs — there is no shared key between the two providers
# for the same real-world match. See _resolve_cricbuzz_match_id() for how
# that gap is bridged (team-name + date matching against Cricbuzz's own
# live-match list).
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
CRICBUZZ_HOST = "cricbuzz-cricket2.p.rapidapi.com"
CRICBUZZ_BASE = f"https://{CRICBUZZ_HOST}"

# Also a 100/day hard limit (confirmed on RapidAPI's Basic/free plan for
# this API, 2026-07-09) — a SEPARATE budget from CricketData.org's 100/day,
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
        "CRICKETDATA_API_KEY is not set. The backend will run but every "
        "refresh cycle will fail and the API will keep serving the last "
        "known cache (empty on first boot). Set this env var on Render."
    )

if not RAPIDAPI_KEY:
    log.warning(
        "RAPIDAPI_KEY is not set. Match detail pages will show scores and "
        "innings but NOT live commentary — that feature requires this key "
        "(Cricbuzz Cricket2 on RapidAPI). Set this env var on Render."
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


def _cricbuzz_get(path: str, params: dict | None = None) -> dict | None:
    """
    Shared fetch helper for the Cricbuzz Cricket2 RapidAPI. Same pattern as
    _cricketdata_get: never called from inside a request handler, only
    from the background refresh loop, so real usage stays inside the
    100/day free-tier budget.
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
    different providers can be compared for a match. CricketData and
    Cricbuzz occasionally differ on things like 'Women' placement or
    trailing tour/series descriptors, so this is intentionally loose."""
    return " ".join(name.lower().replace("-", " ").split())


def _resolve_cricbuzz_match_id(team1_name: str, team2_name: str) -> str | None:
    """
    Bridge the gap between CricketData.org's UUID match IDs and Cricbuzz's
    numeric match IDs — there is no shared identifier between the two
    providers for the same real-world match, confirmed 2026-07-09. This
    fetches Cricbuzz's own live-match list and finds the entry whose two
    team names both appear (in either order) among our target names.

    This costs one Cricbuzz API call. It is only invoked from the
    background refresh loop (never from a request handler), and only the
    first time a given CricketData match_id's detail view is opened —
    the resolved numeric ID is cached alongside the rest of that match's
    detail data, so repeat views cost zero additional resolution calls.
    """
    data = _cricbuzz_get("/mcenter/v1/matches/live")
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
    matching commentaryformats entry. Confirmed real shape:
        commentaryformats: [ {type: "", value: []}, {type: "bold", value: [{id: "B0$", value: "SIX"}]}, ... ]
    Falls back to stripping the raw token if no matching format entry is
    found, rather than leaving something like "B0$" visible to a reader.
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

    # Any leftover unresolved tokens (format list didn't cover them) —
    # strip rather than show raw "B2$" etc. to the reader.
    result = re.sub(r"B\d+\$", "", result)
    result = " ".join(result.split())

    # Wicket rows carry TWO placeholders: a short one ("out") plus a
    # descriptive phrase inline where the ball is described ("Caught by
    # X!!" / "Run Out!!" / "Bowled!!" / "Stumped!!"), and a longer one
    # with the full dismissal detail tacked on after (e.g. "<Batter> c
    # <Fielder> b <Bowler> 14(7) [4s-1 6s-1]" for a catch, or "<Batter>
    # run out (<Fielder>) 0(1)" for a run out). Resolving both literally
    # produces an awkward doubled-up sentence repeating the dismissal type
    # twice. Since the long form already contains everything meaningful,
    # this drops everything up to and including the redundant short
    # descriptive phrase, keeping only the clean scorecard-style line.
    # Confirmed against real caught AND run-out rows on 2026-07-09.
    dismissal_lead_pattern = r".*?(?:caught by [^!]*!!|run out!!|bowled!!|stumped!!)\s*"
    cleaned = re.sub(dismissal_lead_pattern, "", result, flags=re.IGNORECASE)
    if cleaned and cleaned != result:
        result = cleaned.strip()
    else:
        # Fallback for the plain "out <full detail>" shape with no
        # descriptive phrase in between (still redundant: "out" + a full
        # sentence that already states the dismissal).
        result = re.sub(r"^(.*?),\s*out\s+", r"\1, ", result, count=1, flags=re.IGNORECASE)

    return result


def _is_system_announcement(text: str) -> bool:
    """
    Filter out Cricbuzz's short duplicate/system rows that carry no new
    information beyond the real commentary row for the same ball —
    confirmed from real data: "THATS OUT!!", "Caught!!", "Bowled!!",
    "Run Out!!", and player-arrival lines like "<Name> comes to the
    crease" or bowler-change lines like "<Name> is back into the attack".
    These arrive as separate comwrapper entries alongside the real ball
    commentary and would otherwise show as confusing near-duplicate lines
    in the feed.

    Checked as SUBSTRINGS, not exact-string matches — after placeholder
    resolution (_resolve_commentary_placeholders), these system phrases
    often appear inside a longer string like "Bowler to Batter, THATS
    OUT!! Caught!!" rather than standing alone, since Cricbuzz sometimes
    emits the bowler/batter prefix even on what is otherwise a pure
    system-announcement row. An exact-match check missed these; confirmed
    against real data on 2026-07-09.
    """
    t = text.strip().lower()
    system_phrases = ("thats out!!", "caught!!", "bowled!!", "run out!!", "stumped!!")
    if any(phrase in t for phrase in system_phrases) and len(t) < 60:
        # Length guard: a genuine wicket-detail row can legitimately
        # contain "out" as part of a dismissal description, but those
        # rows are long (bowler+batter+shot description). Short rows
        # containing these phrases are the redundant system announcements.
        return True
    if "comes to the crease" in t:
        return True
    if "is back into the attack" in t or "into the attack" in t:
        return True
    return False


def _fetch_cricbuzz_commentary(cricbuzz_match_id: str, innings_id: int = 1) -> list[dict]:
    """
    Fetch ball-by-ball commentary for one innings and shape it into the
    { over, type, text } list LiveCarousel.jsx's commentary rail expects.
    Real field names confirmed against a live match (KNDM vs RRR,
    2026-07-09): commtxt, overnum, eventtype ("WICKET", "FOUR", "SIX",
    "over-break", "NONE", or comma-combinations like "over-break,WICKET").

    TWO REAL QUIRKS FOUND IN THE RAW DATA that needed handling, not just
    passed through — confirmed from the live payload, not guessed:

    1. `commtxt` contains literal placeholder tokens like "B0$" where
       Cricbuzz's own frontend would substitute in the bold text from the
       matching `commentaryformats` entry (e.g. "B0$" -> "SIX", or for
       wickets, "B0$"->"out", "B1$"->"Rahul Radesh c ... b ... 14(7)").
       Passed through raw, the feed would literally show "...to Rahul
       Radesh, B0$" instead of "...to Rahul Radesh, SIX" — visibly broken.
       Fixed below by resolving each B{n}$ token against
       commentaryformats[n].value[0].value.

    2. Cricbuzz emits duplicate/near-duplicate ROWS for the same ball: one
       row with the real commentary text and eventtype set (e.g. "WICKET"),
       immediately followed or preceded by a short system-announcement row
       with generic text like "THATS OUT!!" and eventtype "NONE" that adds
       no information beyond what the real row already says. These are
       filtered out (see _is_system_announcement below) so the feed reads
       as one clean line per ball, not two.
    """
    data = _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/comm", params={"iid": innings_id})
    if data is None:
        return []

    entries = data.get("comwrapper", [])
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

        over = c.get("overnum", 0)
        shaped.append({
            "over": f"{over:.1f}" if isinstance(over, (int, float)) and over else "",
            "type": ctype,
            "text": text,
        })

    # Cricbuzz returns most-recent-first already (confirmed from real
    # response ordering) — keep that order since LiveCarousel's feed
    # renders top-to-bottom as "most recent ball at the top".
    return shaped[:30]  # cap to keep payload light; feed doesn't need full match history


def _shape_match_for_carousel(m: dict) -> dict:
    """
    Map a single entry from GET /currentMatches into the shape
    LiveCarousel.jsx expects for its `matches` array:
        { id, venue, status, matchName, score: {home, away}, chaseNote }

    HOW THIS WAS DEBUGGED (worth keeping — CricketData.org's `inning` label
    field is genuinely unreliable and this will bite again if "fixed" by
    guesswork instead of real payload inspection):

    Confirmed from a real raw response on 2026-07-08, CricketData.org's
    `score` array for a 2-innings match looks like this (Warwickshire vs
    Gloucestershire, real match):

        [
          {"r": 203, "w": 5, "o": 20,   "inning": "warwickshire Inning 1"},
          {"r": 173, "w": 6, "o": 20,   "inning": "Warwickshire,Gloucestershire Inning 1"}
        ]

    Two real problems in that label field, confirmed across many matches
    in the same payload:
      1. The FIRST innings label is lowercased team name ("warwickshire"),
         while `teams[]` gives proper-cased names ("Warwickshire") — so
         case-sensitive prefix matching silently fails on every first
         innings.
      2. The SECOND innings label is not the batting team's name at all —
         it's BOTH team names comma-joined ("Warwickshire,Gloucestershire").
         This appears to be a CricketData.org quirk (possibly meant to show
         "team who batted second, chasing team who bowled first" but
         rendered incorrectly) and NOT something any team-name matching
         logic can parse correctly, because both team names are
         legitimately substrings of that label.

    Given the label field is unreliable in a way that isn't just "slightly
    off" but self-contradictory (attempting name-matching first, then
    positional fallback, gave a match that was WORSE than either approach
    alone — see earlier logs, e.g. it once assigned the same 173/6 score
    to BOTH home and away), the robust fix is to stop trying to parse the
    `inning` string at all. Instead: `score[]` entries are already returned
    in innings-batted order (first team to bat is index 0, second team to
    bat is index 1). We use that positional order directly, which is
    exactly the same technique Roanuz's own API docs recommend for reading
    innings order — this is a known-sane approach for cricket data APIs,
    not a workaround unique to CricketData.org's quirks.
    """
    score_list = m.get("score") or []
    teams = m.get("teams") or []
    home_name = teams[0] if len(teams) > 0 else "TBD"
    away_name = teams[1] if len(teams) > 1 else "TBD"

    # Positional: index 0 = whichever team batted first, index 1 = second.
    # This does NOT necessarily mean index 0 == home_name — cricket does not
    # have a fixed "home bats first" rule, and CricketData.org's `teams[]`
    # order does not reliably indicate batting order either. So rather than
    # mislabel who's "home" vs "away" (which LiveCarousel.jsx only uses for
    # left/right display position, not umpiring correctness), we assign
    # positionally and accept that "home"/"away" here means "batted
    # first"/"batted second", not a true home-ground designation. This is
    # honestly all `home`/`away` ever meant in the original component too,
    # since neutral-venue T20 leagues don't have a real home team most of
    # the time anyway.
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


def _shape_match_details(match_id: str, data: dict, commentary: list[dict] | None = None) -> dict:
    """
    Map GET /match_info?id=... into the shape LiveCarousel.jsx expects
    for a single match drilldown:
        { toss, venue, recentBalls, currentBowler, innings1, innings2, commentary }

    CricketData.org's free tier match_info endpoint does NOT include
    ball-by-ball commentary text (that's a paid-tier feature on most
    cricket data providers, this one included). Everything else (toss,
    venue, innings, batting/bowling figures) IS available on the free tier
    and is mapped from CricketData below.

    `commentary`, if provided, comes from a SEPARATE source — the Cricbuzz
    Cricket2 API on RapidAPI — since that's the only one of our sources
    that actually has ball-by-ball text. See _resolve_cricbuzz_match_id()
    and _fetch_cricbuzz_commentary() for how that's fetched and matched to
    this CricketData match by team name (the two providers use unrelated
    ID schemes, so there's no direct lookup).
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

    # IMPORTANT: return None (not {}) for an innings that hasn't started yet.
    # An empty {} was previously indistinguishable from "data temporarily
    # missing", so the frontend rendered a fake "TBD · 0/0" card for an
    # innings that simply hasn't begun. None lets the frontend cleanly
    # decide to hide that column entirely instead of showing a placeholder.
    innings1 = _shape_innings(innings_list[0]) if len(innings_list) > 0 else None
    innings2 = _shape_innings(innings_list[1]) if len(innings_list) > 1 else None

    return {
        "toss": d.get("tossWinner", "") and f"{d.get('tossWinner')} won, elected to {d.get('tossChoice', '')}",
        "venue": d.get("venue", ""),
        "recentBalls": [],  # not available from either source in a shape recentBalls expects yet
        "commentary": commentary or [],
        "currentBowler": "",  # not reliably present on free tier match_info
        "innings1": innings1,
        "innings2": innings2,
    }


def _refresh_match_detail(match_id: str) -> None:
    data = _cricketdata_get("match_info", {"id": match_id})
    if data is None:
        log.warning("Match detail refresh failed for %s; serving stale cache (if any).", match_id)
        return

    # Resolve (or reuse a previously resolved) Cricbuzz numeric match id for
    # commentary. Resolution costs one Cricbuzz API call and only needs to
    # happen once per match — cache it on the detail entry so repeat
    # refreshes don't re-spend that call.
    with _detail_cache_lock:
        existing_entry = _detail_cache.get(match_id)
        cached_cricbuzz_id = existing_entry.get("cricbuzz_match_id") if existing_entry else None

    cricbuzz_match_id = cached_cricbuzz_id
    if cricbuzz_match_id is None and RAPIDAPI_KEY:
        teams = (data.get("data", {}) or {}).get("teams", [])
        if len(teams) >= 2:
            cricbuzz_match_id = _resolve_cricbuzz_match_id(teams[0], teams[1])
            if cricbuzz_match_id:
                log.info("Resolved Cricbuzz match id %s for %s vs %s", cricbuzz_match_id, teams[0], teams[1])
            else:
                log.info("Could not resolve a Cricbuzz match id for %s vs %s (commentary will stay empty)", teams[0], teams[1])

    commentary = []
    if cricbuzz_match_id:
        # Innings id 1 = first innings. Fetching the currently-relevant
        # innings' commentary is enough for the feed — if this needs to
        # follow innings 2 during a chase, bump this based on
        # innings_list length from CricketData's own response instead of
        # hardcoding, once that's needed.
        innings_list = (data.get("data", {}) or {}).get("scorecard", [])
        innings_id = 2 if len(innings_list) > 1 else 1
        commentary = _fetch_cricbuzz_commentary(cricbuzz_match_id, innings_id=innings_id)

    shaped = _shape_match_details(match_id, data, commentary=commentary)
    with _detail_cache_lock:
        _detail_cache[match_id] = {
            "data": shaped,
            "last_refreshed": datetime.now(timezone.utc).isoformat(),
            "cricbuzz_match_id": cricbuzz_match_id,
        }
    log.info("Refreshed match detail for %s (commentary rows: %d)", match_id, len(commentary))




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
