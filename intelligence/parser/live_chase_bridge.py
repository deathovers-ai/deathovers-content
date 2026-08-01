"""Verified extraction of first-innings context and live chase state."""
from __future__ import annotations

from typing import Any

from chase_state import build_chase_state, cricket_overs_to_legal_balls


def update_first_innings_context(cache: Any, match_id: str, match_format: str, miniscore: dict[str, Any] | None) -> dict[str, Any] | None:
    """Cache innings one only; freeze once the provider has moved to innings two."""
    innings = _innings_scores(miniscore)
    first = next((item for item in innings if item.get("inningsid") == 1), None)
    if not first:
        return None
    runs = _required_int(first, "runs")
    snapshot = {
        "innings": 1,
        "runs": runs,
        "wickets": _required_int(first, "wickets"),
        "legal_balls": _legal_balls(first),
        "target": runs + 1,
        "is_complete": _current_innings_id(miniscore) > 1,
        "format": (match_format or "").upper(),
        "score_source": "miniscore",
    }
    stored = cache.upsert(match_id, snapshot)
    if snapshot["is_complete"]:
        return cache.freeze(match_id)
    return stored


def build_live_chase_from_miniscore(
    match_id: str,
    match_format: str,
    miniscore: dict[str, Any] | None,
    first_innings_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build second-innings facts, preferring the provider target when present.

    No target is inferred when the first innings is unavailable. This prevents
    a partial provider payload from becoming a plausible but wrong chase.
    """
    if _current_innings_id(miniscore) != 2:
        return None
    innings = _innings_scores(miniscore)
    current = next((item for item in innings if item.get("inningsid") == 2), None)
    if not current:
        return None
    provider_target = current.get("target") or (miniscore or {}).get("target")
    cached_target = ((first_innings_context or {}).get("snapshot") or {}).get("target")
    target = provider_target if isinstance(provider_target, int) and provider_target > 0 else cached_target
    if not isinstance(target, int) or target < 1:
        return None
    return build_chase_state(
        match_id=match_id,
        match_format=match_format,
        runs=_required_int(current, "runs"),
        wickets=_required_int(current, "wickets"),
        legal_balls=_legal_balls(current),
        target=target,
    )


def _innings_scores(miniscore: dict[str, Any] | None) -> list[dict[str, Any]]:
    return ((miniscore or {}).get("inningsscores") or {}).get("inningsscore") or []


def _current_innings_id(miniscore: dict[str, Any] | None) -> int:
    value = (miniscore or {}).get("inningsid")
    return value if isinstance(value, int) else 0


def _required_int(value: dict[str, Any], key: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or result < 0:
        raise ValueError(f"miniscore {key} must be a non-negative integer")
    return result


def _legal_balls(score: dict[str, Any]) -> int:
    balls = score.get("balls")
    if isinstance(balls, int) and balls >= 0:
        return balls
    if score.get("overs") is None:
        raise ValueError("miniscore needs balls or overs")
    return cricket_overs_to_legal_balls(score["overs"])
