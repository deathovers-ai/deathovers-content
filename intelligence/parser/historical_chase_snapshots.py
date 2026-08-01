"""Build reproducible second-innings snapshots from DeathOvers event files.

Each output row is the state immediately after a legal delivery in an eligible
limited-overs chase.  The row carries the eventual match outcome, allowing a
later cohort builder to answer historical-recovery questions without peeking
at any future state from the in-progress chase.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from context_repository import normalize_venue


SUPPORTED_FORMATS = {"T20", "IT20", "ODI", "ODM", "IPL"}
FORMAT_BALL_LIMITS = {"T20": 120, "IT20": 120, "IPL": 120, "ODI": 300, "ODM": 300}


def build_chase_snapshots(match: dict[str, Any]) -> list[dict[str, Any]]:
    """Return legal-delivery snapshots for one eligible two-innings match.

    Excludes no-results, ties, revised-target/DLS matches and formats outside
    the initial T20/ODI scope.  The function returns an empty list rather than
    manufacturing a target or result for an ineligible match.
    """
    meta = match.get("meta") or {}
    events = match.get("events") or []
    match_type = (meta.get("match_type") or "").upper()
    competition_code = (meta.get("competition_code") or "").upper()
    snapshot_format = competition_code if competition_code in {"IPL", "IT20"} else match_type
    outcome = meta.get("outcome") or {}

    if match_type not in SUPPORTED_FORMATS or _has_revised_target(outcome):
        return []
    if not outcome.get("winner") or outcome.get("result") in {"tie", "no result", "abandoned"}:
        return []

    innings = defaultdict(list)
    for event in events:
        innings[event.get("innings_num")].append(event)
    first, second = innings.get(1, []), innings.get(2, [])
    if not first or not second:
        return []

    first_runs = sum(_integer(event.get("runs_total")) for event in first)
    batting_team = second[0].get("batting_team")
    if not batting_team:
        return []

    target = first_runs + 1
    total_legal_balls = FORMAT_BALL_LIMITS[snapshot_format]
    chase_won = outcome.get("winner") == batting_team
    final_runs = 0
    final_wickets = 0
    legal_balls = 0
    snapshots = []

    for event in second:
        final_runs += _integer(event.get("runs_total"))
        final_wickets += len(event.get("wickets") or [])
        if not event.get("is_legal_delivery"):
            continue

        legal_balls += 1
        runs_required = max(target - final_runs, 0)
        snapshots.append({
            "schema_version": "historical-chase-snapshot-v1",
            "match_id": str(match.get("match_id") or meta.get("match_id") or ""),
            "format": snapshot_format,
            "venue": normalize_venue(meta.get("venue") or ""),
            "season": meta.get("season"),
            "match_date": (meta.get("dates") or [None])[0],
            "innings": 2,
            "batting_team": batting_team,
            "bowling_team": second[0].get("bowling_team"),
            "target": target,
            "legal_balls": legal_balls,
            "legal_balls_remaining": max(total_legal_balls - legal_balls, 0),
            "runs": final_runs,
            "wickets": final_wickets,
            "runs_required": runs_required,
            "chase_won": chase_won,
            "final_runs": None,  # populated after the final legal delivery is known
            "final_wickets": None,
        })

    for snapshot in snapshots:
        snapshot["final_runs"] = final_runs
        snapshot["final_wickets"] = final_wickets
    return snapshots


def build_from_event_files(event_files: Iterable[Path]) -> Iterable[dict[str, Any]]:
    """Yield rows from parser output files without keeping the corpus in memory."""
    for path in event_files:
        with path.open(encoding="utf-8") as handle:
            match = json.load(handle)
        yield from build_chase_snapshots(match)


def write_jsonl(event_dir: Path, destination: Path) -> int:
    """Generate a newline-delimited dataset and return its row count."""
    files = sorted(event_dir.glob("*.json"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for row in build_from_event_files(files):
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            count += 1
    return count


def _has_revised_target(outcome: dict[str, Any]) -> bool:
    method = str(outcome.get("method") or "").lower()
    return method in {"d/l", "dls", "duckworth lewis", "vjd"}


def _integer(value: Any) -> int:
    if not isinstance(value, int):
        raise ValueError("event runs_total must be an integer")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate historical chase snapshots from event JSON files.")
    parser.add_argument("event_dir", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"Wrote {write_jsonl(args.event_dir, args.destination)} snapshots to {args.destination}")


if __name__ == "__main__":
    main()
