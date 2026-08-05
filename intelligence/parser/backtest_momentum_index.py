"""
F07 backtest — momentum baselines + live insight path.

Usage (from intelligence/parser):
  python3 backtest_momentum_index.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insight_engine import InsightEngine
from momentum_index import (
    MIN_BASELINE_SAMPLES,
    compute_momentum_index,
    load_baselines,
    lookup_percentile,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINES = os.path.join(BASE_DIR, "output", "context", "momentum_baselines.json")
REPORT = os.path.join(BASE_DIR, "output", "context", "f07_backtest_report.json")


def main():
    baselines = load_baselines(BASELINES)
    checks = []
    failures = []

    def check(name, ok, detail=None):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name)

    check("baselines_present", bool(baselines.get("formats")), list((baselines.get("formats") or {})))
    formats = baselines.get("formats") or {}
    for fmt in ("T20", "IPL"):
        check(f"{fmt}_present", fmt in formats, list(formats))
        if fmt not in formats:
            continue
        for phase in ("powerplay", "middle", "death"):
            block = formats[fmt].get(phase) or {}
            n = block.get("n", 0)
            check(f"{fmt}_{phase}_n_ge_{MIN_BASELINE_SAMPLES}", n >= MIN_BASELINE_SAMPLES, n)
            check(f"{fmt}_{phase}_has_p50", block.get("p50") is not None, block.get("p50"))
            check(f"{fmt}_{phase}_has_samples", len(block.get("samples") or []) > 0, len(block.get("samples") or []))

    # Synthetic surge should land high percentile in middle overs.
    hot = [{"runs_total": r, "is_wicket": False} for r in [6, 4, 4, 6, 1, 4, 6, 4, 1, 6, 4, 4, 6, 1, 4, 6, 4, 1]]
    cold = []
    for i, r in enumerate([0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0]):
        cold.append({"runs_total": r, "is_wicket": i in (2, 9) and r == 0})

    hot_i = compute_momentum_index(hot, 120.0)
    cold_i = compute_momentum_index(cold, 120.0)
    check("hot_positive", hot_i is not None and hot_i > 0.3, hot_i)
    check("cold_negative", cold_i is not None and cold_i < 0, cold_i)

    hot_pct = lookup_percentile(baselines, "IPL", "middle", hot_i) if hot_i is not None else None
    cold_pct = lookup_percentile(baselines, "IPL", "middle", cold_i) if cold_i is not None else None
    check("hot_pct_ge_70", hot_pct is not None and hot_pct >= 70, hot_pct)
    check("cold_pct_le_40", cold_pct is not None and cold_pct <= 40, cold_pct)

    eng = InsightEngine(momentum_baselines=baselines, player_stats={}, venue_stats={}, matchup_stats={})
    hit = eng.momentum_index_insight(hot, 120.0, match_type="IPL", phase_name="middle")
    check("insight_fires", hit is not None and hit.get("type") == "momentum_index", hit)
    check("insight_has_percentile", hit and hit.get("percentile") is not None, (hit or {}).get("percentile"))
    check("insight_has_index", hit and -1 <= hit.get("index", 99) <= 1, (hit or {}).get("index"))

    # Thin window silent
    thin = eng.momentum_index_insight([{"runs_total": 1, "is_wicket": False}] * 5, 120.0, "IPL", "middle")
    check("thin_silent", thin is None)

    report = {
        "formats": {fmt: {ph: (formats.get(fmt) or {}).get(ph, {}).get("n") for ph in ("powerplay", "middle", "death")} for fmt in formats},
        "checks": checks,
        "failed": failures,
        "passed": len(failures) == 0,
        "hot_index": hot_i,
        "cold_index": cold_i,
        "hot_pct_ipl_middle": hot_pct,
        "cold_pct_ipl_middle": cold_pct,
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(f"F07 backtest FAILED: {failures}")
    print("F07 backtest PASSED")


if __name__ == "__main__":
    main()
