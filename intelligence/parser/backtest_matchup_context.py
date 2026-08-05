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
from matchup_context import format_dismissal_kinds
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
    missing_meta = 0
    kind_sum_mismatch = 0
    for bowlers in matchups.values():
        for block in bowlers.values():
            if not matchup_is_reliable(block):
                thin += 1
            if block.get("balls", 0) < MIN_MATCHUP_BALLS:
                thin += 1
            if not block.get("years") or not block.get("venues"):
                missing_meta += 1
            kinds = block.get("dismissal_kinds") or {}
            if sum(kinds.values()) != block.get("dismissals", 0):
                kind_sum_mismatch += 1
    check("no_thin_pairs_committed", thin == 0, thin)
    check("all_pairs_have_years_and_venues", missing_meta == 0, missing_meta)
    check("dismissal_kinds_sum_to_dismissals", kind_sum_mismatch == 0, kind_sum_mismatch)

    # Known IPL duel.
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
        check("kohli_bumrah_has_years", bool(bumrah.get("years")), bumrah.get("years"))
        check("kohli_bumrah_has_venues", bool(bumrah.get("venues")), list((bumrah.get("venues") or {}))[:3])

    # Online-validated Rohit vs Rashid card.
    rohit_vs = matchups.get("RG Sharma") or {}
    rashid = rohit_vs.get("Rashid Khan")
    check("rohit_rashid_present", rashid is not None)
    if rashid:
        check("rohit_rashid_balls_44", rashid.get("balls") == 44, rashid.get("balls"))
        check("rohit_rashid_dismissals_4", rashid.get("dismissals") == 4, rashid.get("dismissals"))
        kinds = rashid.get("dismissal_kinds") or {}
        check(
            "rohit_rashid_kinds_2lbw_2caught",
            kinds.get("lbw") == 2 and kinds.get("caught") == 2,
            kinds,
        )
        check(
            "rohit_rashid_breakdown_label",
            format_dismissal_kinds(kinds) == "2 caught + 2 lbw",
            format_dismissal_kinds(kinds),
        )
        years = rashid.get("years") or []
        check("rohit_rashid_years_span", 2017 in years and 2025 in years, years)
        venues = rashid.get("venues") or {}
        check(
            "rohit_rashid_wankhede_present",
            any("Wankhede" in v for v in venues),
            list(venues.keys())[:5],
        )

    engine = InsightEngine(matchup_stats=matchups)
    if bumrah:
        hit = engine.bowler_batter_matchup("V Kohli", "JJ Bumrah")
        check("insight_fires", hit is not None, (hit or {}).get("headline"))
        check("insight_type", hit and hit.get("type") == "bowler_batter_matchup")

    if rashid:
        hit = engine.bowler_batter_matchup("RG Sharma", "Rashid Khan")
        check("rohit_rashid_insight_fires", hit is not None, (hit or {}).get("headline"))
        labels = {p["label"]: p["value"] for p in (hit or {}).get("pointers") or []}
        check("rohit_rashid_pointer_kinds", "lbw" in str(labels.get("Dismissals", "")), labels.get("Dismissals"))
        check("rohit_rashid_pointer_years", "Years" in labels, labels.get("Years"))
        check("rohit_rashid_pointer_venues", "Venues" in labels, labels.get("Venues"))

    # Thin pair must stay silent.
    thin_engine = InsightEngine(
        matchup_stats={"V Kohli": {"Fake Bowler": {
            "balls": 10, "runs": 20, "dismissals": 0,
            "dismissal_kinds": {}, "venues": {}, "years": [],
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
        "rohit_rashid": rashid,
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(f"F06 backtest FAILED: {failures}")
    print("F06 backtest PASSED")


if __name__ == "__main__":
    main()
