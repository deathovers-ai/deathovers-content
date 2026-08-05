"""
F05 offline backtest: calibrate Monte Carlo WP against compact chase index
empirical recovery rates (no raw events required).

Usage:
  python3 backtest_win_probability.py
"""
from __future__ import annotations

import gzip
import json
import math
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
MAX_COMPARE = 400
BALL_LO, BALL_HI = 18, 108
N_SIMS = 500


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
        "legal_balls": legal_balls,
        "target": target_i,
        "wickets": wickets_i,
    }


def _phase_band(legal_balls: int) -> str:
    overs = legal_balls / 6
    if overs < 6:
        return "powerplay"
    if overs < 15:
        return "middle"
    return "death"


def _runs_from_bucket(meta: dict, values: list) -> int:
    """
    Reconstruct a plausible live score for this cohort cell.

    Compact keys omit runs. Prefer successful-chase average runs when present
    (winning-pace state); else ball-fraction proxy.
    # ponytail: winner-pace bias; upgrade when chase_snapshots.jsonl is available.
    """
    n, wins, run_sum = int(values[0]), int(values[1]), float(values[2])
    max_balls = 120
    if wins > 0 and run_sum > 0:
        runs = int(round(run_sum / wins))
    else:
        runs = int(round(meta["target"] * (meta["legal_balls"] / max_balls) * 0.92))
    return max(0, min(runs, meta["target"] - 1))


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation (no scipy)."""
    n = len(xs)
    if n < 3:
        return 0.0

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    deny = math.sqrt(sum((b - my) ** 2 for b in ry))
    if denx == 0 or deny == 0:
        return 0.0
    return num / (denx * deny)


def _monotonicity(dists: dict) -> dict:
    """Same resources, harder target → lower WP; more wickets → lower WP."""
    rng = random.Random(11)
    base = {
        "format": "T20",
        "runs": 90,
        "wickets": 3,
        "legal_balls": 72,
        "legal_balls_remaining": 48,
        "chase_complete": False,
    }
    wps = []
    for target in (140, 160, 180, 200):
        state = {**base, "target": target, "runs_required": target - base["runs"]}
        hit = simulate_chase(state, dists, n_sims=600, rng=random.Random(rng.randint(1, 10**9)))
        wps.append(hit["batting_wp"] if hit else None)
    target_mono = all(
        wps[i] is not None and wps[i + 1] is not None and wps[i] >= wps[i + 1] - 0.03
        for i in range(len(wps) - 1)
    )

    wicket_wps = []
    for wk in (1, 3, 5, 7):
        state = {
            "format": "T20",
            "target": 160,
            "runs": 100,
            "wickets": wk,
            "legal_balls": 72,
            "legal_balls_remaining": 48,
            "runs_required": 60,
            "chase_complete": False,
        }
        hit = simulate_chase(state, dists, n_sims=600, rng=random.Random(rng.randint(1, 10**9)))
        wicket_wps.append(hit["batting_wp"] if hit else None)
    wicket_mono = all(
        wicket_wps[i] is not None
        and wicket_wps[i + 1] is not None
        and wicket_wps[i] >= wicket_wps[i + 1] - 0.03
        for i in range(len(wicket_wps) - 1)
    )
    return {
        "target_ladder_wp": wps,
        "target_monotonic": target_mono,
        "wicket_ladder_wp": wicket_wps,
        "wicket_monotonic": wicket_mono,
    }


def main() -> int:
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

    # --- A. Scenario extremes ---
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

    # --- B. Monotonicity ---
    mono = _monotonicity(dists)
    check("target_monotonic", mono["target_monotonic"], mono["target_ladder_wp"])
    check("wicket_monotonic", mono["wicket_monotonic"], mono["wicket_ladder_wp"])

    # --- C. Cohort calibration ---
    candidates = []
    for key, values in buckets.items():
        meta = _parse_key(key)
        if not meta:
            continue
        n, wins = int(values[0]), int(values[1])
        if n < MIN_BUCKET_N or wins < 1:
            continue
        empirical = wins / n
        if empirical < 0.15 or empirical > 0.85:
            continue
        candidates.append((meta, values, empirical))

    check("enough_candidates", len(candidates) >= 30, len(candidates))
    rng = random.Random(42)
    rng.shuffle(candidates)
    sample = candidates[:MAX_COMPARE]

    abs_errs = []
    signed_errs = []
    rows = []
    by_phase: dict[str, list[float]] = {"powerplay": [], "middle": [], "death": []}

    for meta, values, empirical in sample:
        max_balls = 120
        balls_remaining = max_balls - meta["legal_balls"]
        runs = _runs_from_bucket(meta, values)
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
        seed = (meta["legal_balls"] * 1009 + meta["target"] * 13 + meta["wickets"]) & 0xFFFFFFFF
        wp = simulate_chase(state, dists, venue=None, n_sims=N_SIMS, rng=random.Random(seed))
        if not wp:
            continue
        err = abs(wp["batting_wp"] - empirical)
        signed = wp["batting_wp"] - empirical
        abs_errs.append(err)
        signed_errs.append(signed)
        band = _phase_band(meta["legal_balls"])
        by_phase[band].append(err)
        rows.append(
            {
                "format": meta["format"],
                "legal_balls": meta["legal_balls"],
                "phase": band,
                "target": meta["target"],
                "wickets": meta["wickets"],
                "runs_used": runs,
                "cohort_n": int(values[0]),
                "empirical": round(empirical, 4),
                "mc_wp": wp["batting_wp"],
                "abs_err": round(err, 4),
                "signed_err": round(signed, 4),
            }
        )

    check("compared_rows", len(abs_errs) >= 50, len(abs_errs))
    mae = sum(abs_errs) / len(abs_errs)
    bias = sum(signed_errs) / len(signed_errs)
    spearmen = _spearman([r["empirical"] for r in rows], [r["mc_wp"] for r in rows])
    within_15 = sum(1 for e in abs_errs if e <= 0.15) / len(abs_errs)
    within_25 = sum(1 for e in abs_errs if e <= 0.25) / len(abs_errs)

    phase_mae = {
        phase: round(sum(errs) / len(errs), 4) if errs else None
        for phase, errs in by_phase.items()
    }

    # Winner-pace runs → MC should not be systematically far below empirical.
    # Soft ceiling: MAE < 0.25 with Spearman > 0.25 (rank agreement).
    check("mae_under_ceiling", mae < 0.25, round(mae, 4))
    check("spearman_positive", spearmen > 0.25, round(spearmen, 4))

    report = {
        "schema": "f05-backtest-v2",
        "compared": len(abs_errs),
        "candidate_pool": len(candidates),
        "mae": round(mae, 4),
        "mae_ceiling": 0.25,
        "bias_mc_minus_empirical": round(bias, 4),
        "spearman": round(spearmen, 4),
        "within_15pp": round(within_15, 4),
        "within_25pp": round(within_25, 4),
        "phase_mae": phase_mae,
        "easy_wp": easy["batting_wp"] if easy else None,
        "hard_wp": hard["batting_wp"] if hard else None,
        "monotonicity": mono,
        "dists_file": str(DISTS_FILE),
        "index": str(INDEX_PATH),
        "index_cutoff": payload.get("cutoff"),
        "n_sims_per_row": N_SIMS,
        "worst_rows": sorted(rows, key=lambda r: r["abs_err"], reverse=True)[:10],
        "best_rows": sorted(rows, key=lambda r: r["abs_err"])[:10],
        "sample_rows": rows[:12],
        "notes": (
            "Calibrated vs compact-index recovery_rate at format|*|balls|target|wickets. "
            "Runs reconstructed from successful-chase average in the bucket (winner-pace). "
            "True ball-by-ball backtest needs chase_snapshots.jsonl / events (gitignored)."
        ),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print()
    print("=== F05 backtest summary ===")
    print(f"  cohort rows compared : {len(abs_errs)} (pool {len(candidates)})")
    print(f"  MAE                  : {mae:.4f}  (ceiling 0.25)")
    print(f"  bias (MC − empirical): {bias:+.4f}")
    print(f"  Spearman ρ           : {spearmen:.4f}")
    print(f"  within ±15pp         : {within_15:.1%}")
    print(f"  within ±25pp         : {within_25:.1%}")
    print(f"  phase MAE            : {phase_mae}")
    print(f"  easy / hard WP       : {easy['batting_wp']:.3f} / {hard['batting_wp']:.3f}")
    print(f"  target ladder WP     : {[round(x, 3) for x in mono['target_ladder_wp']]}")
    print(f"  wicket ladder WP     : {[round(x, 3) for x in mono['wicket_ladder_wp']]}")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
