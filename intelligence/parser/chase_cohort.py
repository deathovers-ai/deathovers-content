"""Deterministic comparable-chase cohort selection and metrics."""
from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any, Iterable


def select_cohort(
    snapshots: Iterable[dict[str, Any]],
    state: dict[str, Any],
    *,
    target_tolerance: int,
    wicket_tolerance: int,
    venue: str | None = None,
) -> list[dict[str, Any]]:
    """Select same-format, same-point historical snapshots.

    Tolerances are caller-owned policy values. This module does not invent
    thresholds or fallbacks.
    """
    required = {"format", "legal_balls", "target", "wickets"}
    missing = required - state.keys()
    if missing:
        raise ValueError(f"state is missing: {', '.join(sorted(missing))}")
    if target_tolerance < 0 or wicket_tolerance < 0:
        raise ValueError("tolerances must be non-negative")

    selected = []
    for row in snapshots:
        if row.get("format") != state["format"]:
            continue
        if row.get("legal_balls") != state["legal_balls"]:
            continue
        if abs(row.get("target", -1) - state["target"]) > target_tolerance:
            continue
        if abs(row.get("wickets", -1) - state["wickets"]) > wicket_tolerance:
            continue
        if venue is not None and row.get("venue") != venue:
            continue
        selected.append(row)
    return selected


def summarize_cohort(cohort: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    """Return facts only. Confidence thresholds belong to the validator."""
    if not cohort:
        return {"sample_size": 0, "wins": 0, "recovery_rate": None}
    wins = sum(1 for row in cohort if row.get("chase_won"))
    successful = [row for row in cohort if row.get("chase_won")]
    median_runs = median(row["runs"] for row in successful) if successful else None
    median_wickets = median(row["wickets"] for row in successful) if successful else None
    rrr_values = [
        row["runs_required"] / row["legal_balls_remaining"] * 6
        for row in successful
        if row.get("legal_balls_remaining", 0) > 0
    ]
    return {
        "sample_size": len(cohort),
        "wins": wins,
        "recovery_rate": wins / len(cohort),
        "median_successful_runs": median_runs,
        "median_successful_wickets": median_wickets,
        "median_successful_rrr": median(rrr_values) if rrr_values else None,
        "pace_gap_runs": (state["runs"] - median_runs) if median_runs is not None else None,
        "wicket_gap": (state["wickets"] - median_wickets) if median_wickets is not None else None,
    }
