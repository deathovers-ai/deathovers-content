"""
app.py — DeathOvers live-data backend (v4)

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


def _fetch_cricbuzz_commentary_and_miniscore(cricbuzz_match_id: str, innings_id: int = 1) -> dict:
    data = _cricbuzz_get(f"/mcenter/v1/{cricbuzz_match_id}/comm", params={"iid": innings_id})
    if data is None:
        return {"commentary": [], "miniscore": None}

    entries = data.get("comwrapper", [])
    miniscore = data.get("miniscore")
    log.info("DEBUG raw response top-level keys: %s | miniscore value: %s", list(data.keys()), miniscore)
    oversep_entries = [e.get("commentary", {}).get("oversep") for e in entries if e.get("commentary", {}).get("oversep")]
    log.info("DEBUG found %s oversep blocks in this response. First one: %s", len(oversep_entries), oversep_entries[0] if oversep_entries else None)
    shaped = []

    for entry in entries:
        c = entry.get("commentary", {})
        raw_text = (c.get("commtxt") or "").strip()
        if not raw_text:
            continue
        text =
