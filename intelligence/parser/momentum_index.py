"""
F07 — continuous Momentum Index (−1..+1) + Cricsheet percentile baselines.

Reuses the same recent-ball window idea as situation acceleration
(last 18 legal balls) but produces a signed continuous index instead of
a one-sided 0–100 score. Discrete situation_* insights stay unchanged.

Baselines: for each format × phase, store empirical percentiles of the
index from rolling windows over the T20/IPL event corpus.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import determine_phase_from_over
from context_freshness import write_context_meta
from player_context import EVENTS_DIR, MANIFEST, competition_code_for_match

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
BASELINES_FILE = os.path.join(CONTEXT_DIR, "momentum_baselines.json")

WINDOW = 18
MIN_WINDOW = 12
MIN_BASELINE_SAMPLES = 200
MATCHUP_FORMATS = {"T20", "IT20", "IPL"}
PERCENTILE_KEYS = (10, 25, 50, 75, 90)


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_momentum_index(recent_balls: list[dict], innings_avg_strike_rate: float) -> float | None:
    """
    Continuous momentum in [-1, +1] from the last WINDOW legal balls.

    Positive: SR above innings average + boundary flow.
    Negative: SR below average, wickets, heavy dots.
    Returns None if the window is too thin.
    """
    if not recent_balls or innings_avg_strike_rate is None or innings_avg_strike_rate <= 0:
        return None
    window = recent_balls[-WINDOW:]
    if len(window) < MIN_WINDOW:
        return None

    n = len(window)
    runs = sum(int(b.get("runs_total") or 0) for b in window)
    wickets = sum(1 for b in window if b.get("is_wicket"))
    boundaries = sum(1 for b in window if int(b.get("runs_total") or 0) in (4, 6))
    dots = sum(
        1 for b in window
        if int(b.get("runs_total") or 0) == 0 and not b.get("is_wicket")
    )

    window_sr = (runs / n) * 100
    sr_ratio = (window_sr / innings_avg_strike_rate) - 1.0  # 0 = on pace
    boundary_rate = boundaries / n
    wicket_rate = wickets / n
    dot_rate = dots / n

    # Weights tuned so a hot boundary burst without wickets approaches +1,
    # and a collapse/dot drought approaches -1. Ceiling named for upgrade.
    # ponytail: linear blend; upgrade to logistic calibration vs held-out if needed.
    raw = (
        0.45 * _clip(sr_ratio / 0.40)
        + 0.30 * _clip((boundary_rate - 0.12) / 0.18)
        - 0.15 * _clip(wicket_rate / 0.12, 0.0, 1.0)
        - 0.10 * _clip((dot_rate - 0.35) / 0.35, 0.0, 1.0)
    )
    return round(_clip(raw), 3)


def momentum_label(index: float) -> str:
    if index >= 0.55:
        return "SURGING"
    if index >= 0.20:
        return "BUILDING"
    if index > -0.20:
        return "EVEN"
    if index > -0.55:
        return "STALLING"
    return "SLUMPING"


def _percentile_rank(sorted_vals: list[float], x: float) -> float:
    """Empirical percentile of x within sorted_vals (0–100)."""
    if not sorted_vals:
        return 50.0
    # Fraction of samples strictly below x, plus half of equals.
    below = 0
    equal = 0
    for v in sorted_vals:
        if v < x:
            below += 1
        elif v == x:
            equal += 1
        else:
            break
    return round(100.0 * (below + 0.5 * equal) / len(sorted_vals), 1)


def _quantiles(sorted_vals: list[float]) -> dict:
    n = len(sorted_vals)
    out = {"n": n}
    if n == 0:
        return out
    for p in PERCENTILE_KEYS:
        # nearest-rank
        idx = min(n - 1, max(0, math.ceil(p / 100.0 * n) - 1))
        out[f"p{p}"] = round(sorted_vals[idx], 3)
    return out


def lookup_percentile(baselines: dict, match_type: str, phase: str, index: float) -> float | None:
    block = ((baselines.get("formats") or {}).get(match_type) or {}).get(phase)
    if not block or block.get("n", 0) < MIN_BASELINE_SAMPLES:
        return None
    samples = block.get("samples")
    if samples:
        return _percentile_rank(samples, index)
    # Compact baselines: interpolate from stored quantiles only.
    points = [(p, block.get(f"p{p}")) for p in PERCENTILE_KEYS if block.get(f"p{p}") is not None]
    if len(points) < 2:
        return None
    if index <= points[0][1]:
        return float(points[0][0])
    if index >= points[-1][1]:
        return float(points[-1][0])
    for (p0, v0), (p1, v1) in zip(points, points[1:]):
        if v0 <= index <= v1 and v1 != v0:
            t = (index - v0) / (v1 - v0)
            return round(p0 + t * (p1 - p0), 1)
    return 50.0


def build_momentum_insight(
    recent_balls: list[dict],
    innings_avg_strike_rate: float,
    match_type: str | None,
    phase_name: str | None,
    baselines: dict | None = None,
) -> dict | None:
    index = compute_momentum_index(recent_balls, innings_avg_strike_rate)
    if index is None:
        return None

    label = momentum_label(index)
    percentile = None
    if baselines and match_type and phase_name:
        percentile = lookup_percentile(baselines, match_type, phase_name, index)

    pointers = [
        {"label": "Momentum", "value": index},
        {"label": "Reading", "value": label},
        {"label": "Window", "value": min(len(recent_balls), WINDOW), "unit": " balls"},
    ]
    if percentile is not None:
        pointers.append({"label": "Phase percentile", "value": percentile, "unit": "th"})
    if phase_name:
        pointers.append({"label": "Phase", "value": phase_name})

    direction = "with batting side" if index >= 0 else "with bowling side"
    headline = f"Momentum {label.lower()} ({index:+.2f}) — {direction}"
    if percentile is not None and phase_name:
        headline = (
            f"Momentum {label.lower()} ({index:+.2f}) — "
            f"{percentile:.0f}th pct in {phase_name}"
        )

    return {
        "type": "momentum_index",
        "index": index,
        "label": label,
        "percentile": percentile,
        "phase": phase_name,
        "match_type": match_type,
        "window_balls": min(len(recent_balls), WINDOW),
        "gauge": {
            "level": (
                "CRITICAL" if abs(index) >= 0.55 else
                "HIGH" if abs(index) >= 0.35 else
                "MODERATE" if abs(index) >= 0.20 else
                "LOW"
            )
        },
        "headline": headline,
        "pointers": pointers,
    }


def build_baselines(
    events_dir: str = EVENTS_DIR,
    manifest_path: str = MANIFEST,
    out_path: str = BASELINES_FILE,
    formats: set[str] | None = None,
    keep_samples: bool = False,
):
    """
    Walk event files; for every rolling WINDOW inside an innings, record
    the momentum index tagged by format + phase. Write compact quantiles
    (optionally retain sample lists for exact percentile lookup — large).
    """
    formats = formats or MATCHUP_FORMATS
    manifest_by_id = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            for row in json.load(f):
                manifest_by_id[str(row["match_id"])] = row

    paths = [
        os.path.join(events_dir, n)
        for n in os.listdir(events_dir)
        if n.endswith(".json")
    ] if os.path.isdir(events_dir) else []
    if not paths:
        raise SystemExit(f"No event files in {events_dir}")

    # format -> phase -> list[float]
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    corpus_through = None
    matches_used = 0

    for i, path in enumerate(sorted(paths), 1):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("meta") or {}
        match_id = str(meta.get("match_id") or os.path.splitext(os.path.basename(path))[0])
        man = manifest_by_id.get(match_id) or {}
        code = competition_code_for_match(meta, man.get("competition_code"))
        if code not in formats:
            continue
        matches_used += 1
        dates = meta.get("dates") or []
        if dates:
            d = dates[-1]
            if corpus_through is None or d > corpus_through:
                corpus_through = d

        # per-innings sliding state
        innings_state: dict[int, dict] = {}
        for event in data.get("events") or []:
            # Align with live recent_balls / matchup batter-facing rule: skip wides.
            if event.get("extra_type") == "wides":
                continue

            inn = int(event.get("innings_num") or 1)
            st = innings_state.setdefault(inn, {
                "balls": [],
                "cum_runs": 0,
                "cum_balls": 0,
            })
            ball = {
                "runs_total": int(event.get("runs_total") or 0),
                "is_wicket": bool(event.get("is_wicket")),
                "over": int(event.get("over") or 0),
            }
            st["balls"].append(ball)
            st["cum_runs"] += ball["runs_total"]
            st["cum_balls"] += 1

            if st["cum_balls"] < MIN_WINDOW:
                continue
            avg_sr = (st["cum_runs"] / st["cum_balls"]) * 100
            if avg_sr <= 0:
                continue
            idx = compute_momentum_index(st["balls"], avg_sr)
            if idx is None:
                continue
            phase = determine_phase_from_over(ball["over"], code)
            if phase is None:
                continue
            buckets[code][phase].append(idx)

        if i % 1000 == 0:
            print(f"  scanned {i}/{len(paths)}...")

    formats_out = {}
    for fmt, phases in buckets.items():
        formats_out[fmt] = {}
        for phase, vals in phases.items():
            vals.sort()
            q = _quantiles(vals)
            # Downsample for exact percentile rank at runtime (small file).
            max_keep = 2500
            if len(vals) > max_keep:
                step = len(vals) / max_keep
                q["samples"] = [vals[int(i * step)] for i in range(max_keep)]
            else:
                q["samples"] = vals
            formats_out[fmt][phase] = q

    out = {
        "window": WINDOW,
        "min_window": MIN_WINDOW,
        "min_baseline_samples": MIN_BASELINE_SAMPLES,
        "matches_used": matches_used,
        "formats": formats_out,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    write_context_meta(corpus_through)
    print(f"Wrote momentum baselines → {out_path} (matches={matches_used})")
    for fmt, phases in formats_out.items():
        for phase, q in phases.items():
            print(f"  {fmt}/{phase}: n={q.get('n')} p50={q.get('p50')}")
    return out


def load_baselines(path: str = BASELINES_FILE) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Build F07 momentum percentile baselines.")
    cli.add_argument("--out", default=BASELINES_FILE)
    cli.add_argument("--events-dir", default=EVENTS_DIR)
    cli.add_argument("--manifest", default=MANIFEST)
    cli.add_argument("--keep-samples", action="store_true")
    args = cli.parse_args()
    build_baselines(
        events_dir=args.events_dir,
        manifest_path=args.manifest,
        out_path=args.out,
        keep_samples=args.keep_samples,
    )
