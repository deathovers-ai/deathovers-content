"""
F06 backtest — run against committed matchup_stats before deploy.

Usage (from intelligence/parser):
  python3 backtest_matchup_context.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insight_engine import InsightEngine
from validation_engine import MIN_MATCHUP_BALLS, matchup_is_reliable

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHUP_STATS = os.path.join(BASE_DIR, "output", "context", "matchup_stats.json")
REPORT = os.path.join(BASE_DIR, "output", "context", "f06_backtest_report.json")


def main():
    with open(MATCHUP_STATS, encoding="utf-8") as f:
        matchups = json.load(f)

    checks = []
    failures = []

    def check(name, ok, detail=None):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name)

    pair_count = sum(len(bowlers) for bowlers in matchups.values())
    check("pairs_gt_500", pair_count > 500, pair_count)
    check("batters_gt_100", len(matchups) > 100, len(matchups))

    thin = 0
    for bowlers in matchups.values():
        for block in bowlers.values():
            if not matchup_is_reliable(block):
                thin += 1
            if block.get("balls", 0) < MIN_MATCHUP_BALLS:
                thin += 1
    check("no_thin_pairs_committed", thin == 0, thin)

    # Known IPL duel should exist with a usable sample when corpus is T20+IPL.
    kohli_vs = matchups.get("V Kohli") or {}
    bumrah = kohli_vs.get("JJ Bumrah")
    check("kohli_bumrah_present", bumrah is not None, list(kohli_vs.keys())[:8])
    if bumrah:
        check("kohli_bumrah_reliable", matchup_is_reliable(bumrah), bumrah)
        check(
            "kohli_bumrah_balls_ge_30",
            bumrah.get("balls", 0) >= MIN_MATCHUP_BALLS,
            bumrah.get("balls"),
        )

    engine = InsightEngine(matchup_stats=matchups)
    if bumrah:
        hit = engine.bowler_batter_matchup("V Kohli", "JJ Bumrah")
        check("insight_fires", hit is not None, (hit or {}).get("headline"))
        check("insight_type", hit and hit.get("type") == "bowler_batter_matchup")

    # Thin pair must stay silent.
    thin_engine = InsightEngine(
        matchup_stats={"V Kohli": {"Fake Bowler": {
            "balls": 10, "runs": 20, "dismissals": 0,
            "strike_rate": 200.0, "average": None, "reliable": False,
        }}},
        player_stats={},
        venue_stats={},
    )
    check("thin_refused", thin_engine.bowler_batter_matchup("V Kohli", "Fake Bowler") is None)

    report = {
        "batter_count": len(matchups),
        "pair_count": pair_count,
        "checks": checks,
        "failed": failures,
        "passed": len(failures) == 0,
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(f"F06 backtest FAILED: {failures}")
    print("F06 backtest PASSED")


if __name__ == "__main__":
    main()
