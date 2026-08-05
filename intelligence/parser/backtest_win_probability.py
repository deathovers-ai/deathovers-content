"""
F05 offline backtest: calibrate Monte Carlo WP against compact chase index
empirical recovery rates (no raw events required).

Usage:
  python3 backtest_win_probability.py
"""
from __future__ import annotations

import gzip
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from win_probability import (
    DISTS_FILE,
    build_phase_distributions,
    load_phase_distributions,
    save_phase_distributions,
    simulate_chase,
)

BASE_DIR = Path(__file__).resolve().parents[1]
INDEX_PATH = BASE_DIR / "output" / "compact_chase_index.json.gz"
REPORT_PATH = BASE_DIR / "output" / "context" / "f05_backtest_report.json"

# Compact index is sparse per venue; calibrate on format-global (*) cohorts.
MIN_BUCKET_N = 15
MAX_COMPARE = 100
BALL_LO, BALL_HI = 18, 108  # skip very first overs + last-ball noise


def check(name: str, ok: bool, detail=None) -> None:
    status = "PASS" if ok else "FAIL"
    extra = f" — {detail}" if detail is not None else ""
    print(f"[{status}] {name}{extra}")
    if not ok:
        raise SystemExit(1)


def _parse_key(key: str) -> dict | None:
    # format|venue_or_*|legal_balls|target|wickets
    parts = key.split("|")
    if len(parts) != 5:
        return None
    fmt, venue, balls, target, wickets = parts
    if venue != "*":
        return None  # format-global only — venue cells are usually n=1
    try:
        legal_balls = int(balls)
        target_i = int(target)
        wickets_i = int(wickets)
    except ValueError:
        return None
    if fmt not in {"T20", "IPL"}:
        return None
    if not (BALL_LO <= legal_balls <= BALL_HI):
        return None
    if wickets_i >= 9:
        return None
    return {
        "format": fmt,
        "venue": None,
        "legal_balls": legal_balls,
        "target": target_i,
        "wickets": wickets_i,
    }


def main() -> int:
    # Ensure dists exist (build from venue_stats if missing).
    dists = load_phase_distributions()
    if dists is None:
        dists = build_phase_distributions()
        save_phase_distributions(dists)
        dists = load_phase_distributions()
    fmts = (dists or {}).get("formats") or {}
    check("dists_loaded", bool(dists) and ("T20" in fmts or "IPL" in fmts))

    with gzip.open(INDEX_PATH, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    check("index_schema", payload.get("schema_version") == "compact-chase-index-v1")
    buckets = payload["buckets"]

    candidates = []
    for key, values in buckets.items():
        meta = _parse_key(key)
        if not meta:
            continue
        n, wins = int(values[0]), int(values[1])
        if n < MIN_BUCKET_N:
            continue
        empirical = wins / n
        # Skip near-certain extremes for a fair mid-band calibration check.
        if empirical < 0.15 or empirical > 0.85:
            continue
        candidates.append((meta, n, empirical))

    check("enough_candidates", len(candidates) >= 30, len(candidates))
    rng = random.Random(42)
    rng.shuffle(candidates)
    sample = candidates[:MAX_COMPARE]

    abs_errs = []
    rows = []
    for meta, n, empirical in sample:
        max_balls = 120
        balls_remaining = max_balls - meta["legal_balls"]
        # Unknown exact runs at snapshot — approximate from required rate midpoints.
        # Compact index keys lack current runs; reconstruct a plausible score
        # using cohort average successful pace is unavailable per-bucket for
        # failures. Use target progress proxy: assume ~required_rr * overs_done
        # scaled — better: runs ≈ target * (legal_balls / max_balls) * 0.95.
        # ponytail: runs proxy from ball fraction; upgrade when snapshots.jsonl ships.
        runs = int(round(meta["target"] * (meta["legal_balls"] / max_balls) * 0.92))
        runs = min(runs, meta["target"] - 1)
        state = {
            "format": meta["format"],
            "target": meta["target"],
            "runs": runs,
            "wickets": meta["wickets"],
            "legal_balls": meta["legal_balls"],
            "legal_balls_remaining": balls_remaining,
            "runs_required": meta["target"] - runs,
            "chase_complete": False,
        }
        wp = simulate_chase(
            state,
            dists,
            venue=None,
            n_sims=400,
            rng=random.Random((meta["legal_balls"] * 1009 + meta["target"] * 13 + meta["wickets"]) & 0xFFFFFFFF),
        )
        if not wp:
            continue
        err = abs(wp["batting_wp"] - empirical)
        abs_errs.append(err)
        rows.append(
            {
                "format": meta["format"],
                "legal_balls": meta["legal_balls"],
                "target": meta["target"],
                "wickets": meta["wickets"],
                "cohort_n": n,
                "empirical": round(empirical, 4),
                "mc_wp": wp["batting_wp"],
                "abs_err": round(err, 4),
            }
        )

    check("compared_rows", len(abs_errs) >= 20, len(abs_errs))
    mae = sum(abs_errs) / len(abs_errs)
    # Directional sanity on the same synthetic states used in unit tests.
    easy = simulate_chase(
        {
            "format": "T20",
            "target": 160,
            "runs": 145,
            "wickets": 2,
            "legal_balls": 96,
            "legal_balls_remaining": 24,
            "runs_required": 15,
            "chase_complete": False,
        },
        dists,
        n_sims=800,
        rng=random.Random(1),
    )
    hard = simulate_chase(
        {
            "format": "T20",
            "target": 180,
            "runs": 70,
            "wickets": 7,
            "legal_balls": 96,
            "legal_balls_remaining": 24,
            "runs_required": 110,
            "chase_complete": False,
        },
        dists,
        n_sims=800,
        rng=random.Random(1),
    )
    check("easy_wp_high", easy and easy["batting_wp"] > 0.75, easy and easy["batting_wp"])
    check("hard_wp_low", hard and hard["batting_wp"] < 0.2, hard and hard["batting_wp"])
    # ponytail: MAE ceiling vs compact-index with runs proxy; tighten when snapshots available.
    check("mae_under_ceiling", mae < 0.28, round(mae, 4))

    report = {
        "schema": "f05-backtest-v1",
        "compared": len(abs_errs),
        "mae": round(mae, 4),
        "mae_ceiling": 0.28,
        "easy_wp": easy["batting_wp"] if easy else None,
        "hard_wp": hard["batting_wp"] if hard else None,
        "dists_file": str(DISTS_FILE),
        "index": str(INDEX_PATH),
        "sample_rows": rows[:15],
        "notes": (
            "Calibration vs compact chase recovery_rate at matched format/venue/balls/target/wickets. "
            "Current runs proxied from ball fraction (events/snapshots absent in this env)."
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"MAE={mae:.4f} on {len(abs_errs)} buckets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
