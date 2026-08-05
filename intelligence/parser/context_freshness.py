"""
F03 — context data freshness.

Tracks when venue/player context was built and how far the corpus reaches.
Uses a small sidecar file so we do not rewrite multi-MB stats JSON or break
callers that iterate venue/player keys.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
META_FILE = os.path.join(CONTEXT_DIR, "context_meta.json")
VENUE_STATS_FILE = os.path.join(CONTEXT_DIR, "venue_stats.json")
PLAYER_STATS_FILE = os.path.join(CONTEXT_DIR, "player_stats.json")

STALE_AFTER_DAYS = 14
META_KEY = "_meta"  # reserved if ever inlined into a stats blob


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_meta(corpus_through: str | None, generated_at: str | None = None) -> dict:
    return {
        "generated_at": generated_at or utc_now_iso(),
        "corpus_through": corpus_through,
    }


def write_context_meta(corpus_through: str | None, path: str = META_FILE) -> dict:
    meta = build_meta(corpus_through)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    return meta


def read_context_meta(path: str = META_FILE) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    # Support either a bare meta object or {"_meta": {...}}
    if META_KEY in data and isinstance(data[META_KEY], dict):
        data = data[META_KEY]
    if "generated_at" not in data and "corpus_through" not in data:
        return None
    return data


def infer_corpus_through_from_players(player_stats: dict | None = None) -> str | None:
    if player_stats is None:
        if not os.path.exists(PLAYER_STATS_FILE):
            return None
        with open(PLAYER_STATS_FILE, encoding="utf-8") as f:
            player_stats = json.load(f)
    latest = None
    for name, entry in player_stats.items():
        if name == META_KEY or not isinstance(entry, dict):
            continue
        date = entry.get("latest_match_date")
        if date and (latest is None or date > latest):
            latest = date
    return latest


def _file_mtime_iso(path: str) -> str | None:
    try:
        ts = os.path.getmtime(path)
    except OSError:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_meta() -> dict:
    """Prefer sidecar; else infer from player_stats + file mtimes."""
    meta = read_context_meta()
    if meta:
        return {
            "generated_at": meta.get("generated_at"),
            "corpus_through": meta.get("corpus_through"),
            "source": "context_meta",
        }

    corpus_through = infer_corpus_through_from_players()
    mtimes = [t for t in (_file_mtime_iso(VENUE_STATS_FILE), _file_mtime_iso(PLAYER_STATS_FILE)) if t]
    generated_at = max(mtimes) if mtimes else None
    return {
        "generated_at": generated_at,
        "corpus_through": corpus_through,
        "source": "inferred",
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # Allow plain YYYY-MM-DD for corpus_through comparisons
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def is_stale(generated_at: str | None, *, now: datetime | None = None, days: int = STALE_AFTER_DAYS) -> bool:
    dt = _parse_iso(generated_at)
    if dt is None:
        return False  # unknown != stale alarm; UI shows "Freshness unknown"
    now = now or datetime.now(timezone.utc)
    return (now - dt) > timedelta(days=days)


def freshness_payload(meta: dict | None = None, *, now: datetime | None = None) -> dict:
    """Shape attached to match-details intelligence.data_freshness."""
    meta = meta or resolve_meta()
    generated_at = meta.get("generated_at")
    corpus_through = meta.get("corpus_through")
    known = bool(generated_at or corpus_through)
    stale = is_stale(generated_at, now=now) if generated_at else False
    return {
        "generated_at": generated_at,
        "corpus_through": corpus_through,
        "stale": stale,
        "stale_after_days": STALE_AFTER_DAYS,
        "known": known,
        "source": meta.get("source", "context_meta"),
    }
