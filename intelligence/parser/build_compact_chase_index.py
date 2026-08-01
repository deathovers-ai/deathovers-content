"""Build a compact, recent-only cohort index for Free Render deployments."""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


def build_index(snapshot_path: Path, destination: Path, cutoff: str) -> dict:
    # [all, wins, successful_runs_sum, successful_wickets_sum, successful_rrr_sum]
    buckets = defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0])
    with snapshot_path.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if (row.get("match_date") or "") < cutoff:
                continue
            for venue in (row.get("venue") or "", "*"):
                key = "|".join(str(part) for part in (
                    row["format"], venue, row["legal_balls"], row["target"], row["wickets"],
                ))
                stats = buckets[key]
                stats[0] += 1
                if row["chase_won"]:
                    stats[1] += 1
                    stats[2] += row["runs"]
                    stats[3] += row["wickets"]
                    if row["legal_balls_remaining"]:
                        stats[4] += row["runs_required"] / row["legal_balls_remaining"] * 6

    payload = {"schema_version": "compact-chase-index-v1", "cutoff": cutoff, "buckets": buckets}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destination, "wt", encoding="utf-8") as output:
        json.dump(payload, output, separators=(",", ":"))
    return {"bucket_count": len(buckets), "cutoff": cutoff}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshots", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--cutoff", default=(date.today() - timedelta(days=365 * 3)).isoformat())
    args = parser.parse_args()
    print(build_index(args.snapshots, args.destination, args.cutoff))
