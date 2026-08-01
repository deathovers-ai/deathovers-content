"""Normalize a live second-innings score into deterministic chase facts."""
from __future__ import annotations

from typing import Any


FORMAT_BALL_LIMITS = {"T20": 120, "IT20": 120, "IPL": 120, "ODI": 300, "ODM": 300}


def build_chase_state(
    *,
    match_id: str,
    match_format: str,
    runs: int,
    wickets: int,
    legal_balls: int,
    target: int,
) -> dict[str, Any]:
    match_format = (match_format or "").upper()
    if match_format not in FORMAT_BALL_LIMITS:
        raise ValueError("unsupported chase format")
    if not str(match_id).strip():
        raise ValueError("match_id is required")
    for name, value in {"runs": runs, "wickets": wickets, "legal_balls": legal_balls, "target": target}.items():
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if target < 1 or wickets > 10:
        raise ValueError("invalid target or wicket count")
    total_balls = FORMAT_BALL_LIMITS[match_format]
    if legal_balls > total_balls:
        raise ValueError("legal_balls exceeds format limit")

    runs_required = max(target - runs, 0)
    balls_remaining = total_balls - legal_balls
    required_run_rate = (
        runs_required / balls_remaining * 6 if runs_required and balls_remaining else 0.0
    )
    return {
        "schema_version": "live-chase-state-v1",
        "match_id": str(match_id),
        "format": match_format,
        "target": target,
        "runs": runs,
        "wickets": wickets,
        "legal_balls": legal_balls,
        "legal_balls_remaining": balls_remaining,
        "runs_required": runs_required,
        "required_run_rate": required_run_rate,
        "chase_complete": runs_required == 0 or balls_remaining == 0 or wickets == 10,
    }


def cricket_overs_to_legal_balls(overs: str | float | int) -> int:
    """Convert cricket notation (e.g. 17.3) without treating it as decimal."""
    text = str(overs)
    if "." in text:
        whole, ball = text.split(".", 1)
    else:
        whole, ball = text, "0"
    if not whole.isdigit() or not ball.isdigit() or int(ball) > 5:
        raise ValueError("invalid cricket overs notation")
    return int(whole) * 6 + int(ball)
