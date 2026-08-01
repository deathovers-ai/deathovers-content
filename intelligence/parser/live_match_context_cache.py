"""Short-lived, match-scoped first-innings context for the Chase Engine.

This cache is deliberately separate from historical data.  It retains only
the compact context required to analyse the second innings of the same match,
then expires it.  It never writes raw commentary or live stage data to a
permanent store.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable


DEFAULT_TTL = timedelta(hours=24)


class FirstInningsContextCache:
    """Thread-safe in-memory cache, suitable for a single backend instance.

    A multi-instance deployment must provide the same interface using a
    shared TTL cache (for example Redis).  Callers cannot mutate stored data:
    all writes and reads are copied.
    """

    def __init__(
        self,
        ttl: timedelta = DEFAULT_TTL,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be positive")
        self._ttl = ttl
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._entries: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def upsert(self, match_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Create or update a first-innings snapshot before it is frozen."""
        key = self._key(match_id)
        self._validate_snapshot(snapshot)
        now = self._utc_now()
        with self._lock:
            existing = self._entries.get(key)
            if existing and self._is_expired(existing, now):
                del self._entries[key]
                existing = None
            if existing and existing["frozen"]:
                return self._public(existing)

            entry = {
                "snapshot": deepcopy(snapshot),
                "frozen": False,
                "stored_at": now,
                "expires_at": now + self._ttl,
            }
            self._entries[key] = entry
            return self._public(entry)

    def freeze(self, match_id: str) -> dict[str, Any] | None:
        """Freeze the verified first-innings context once the target is known."""
        key = self._key(match_id)
        now = self._utc_now()
        with self._lock:
            entry = self._entries.get(key)
            if not entry or self._is_expired(entry, now):
                self._entries.pop(key, None)
                return None
            if not entry["snapshot"].get("is_complete"):
                raise ValueError("cannot freeze an incomplete first-innings snapshot")
            entry["frozen"] = True
            return self._public(entry)

    def get(self, match_id: str) -> dict[str, Any] | None:
        key = self._key(match_id)
        now = self._utc_now()
        with self._lock:
            entry = self._entries.get(key)
            if not entry or self._is_expired(entry, now):
                self._entries.pop(key, None)
                return None
            return self._public(entry)

    def invalidate(self, match_id: str) -> None:
        """Remove a match context after abandonment or provider correction."""
        with self._lock:
            self._entries.pop(self._key(match_id), None)

    def cleanup_expired(self) -> int:
        now = self._utc_now()
        with self._lock:
            expired = [key for key, entry in self._entries.items() if self._is_expired(entry, now)]
            for key in expired:
                del self._entries[key]
            return len(expired)

    @staticmethod
    def _key(match_id: str) -> str:
        if not str(match_id).strip():
            raise ValueError("match_id is required")
        return str(match_id)

    @staticmethod
    def _validate_snapshot(snapshot: dict[str, Any]) -> None:
        required = {"innings", "runs", "wickets", "legal_balls", "target", "is_complete"}
        missing = required - snapshot.keys()
        if missing:
            raise ValueError(f"first-innings snapshot is missing: {', '.join(sorted(missing))}")
        if snapshot["innings"] != 1:
            raise ValueError("only innings 1 can be stored in the first-innings cache")
        for field in ("runs", "wickets", "legal_balls", "target"):
            if not isinstance(snapshot[field], int) or snapshot[field] < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if snapshot["target"] <= snapshot["runs"]:
            raise ValueError("target must exceed the first-innings runs")

    def _utc_now(self) -> datetime:
        now = self._now()
        if now.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)

    @staticmethod
    def _is_expired(entry: dict[str, Any], now: datetime) -> bool:
        return entry["expires_at"] <= now

    @staticmethod
    def _public(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "snapshot": deepcopy(entry["snapshot"]),
            "frozen": entry["frozen"],
            "stored_at": entry["stored_at"].isoformat(),
            "expires_at": entry["expires_at"].isoformat(),
        }
