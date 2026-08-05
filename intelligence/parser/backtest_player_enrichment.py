"""
F04 backtest — run against enriched player_stats before deploy.

Usage (from intelligence/parser):
  python3 backtest_player_enrichment.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insight_engine import InsightEngine
from validation_engine import player_phase_is_reliable, player_venue_is_reliable

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYER_STATS = os.path.join(BASE_DIR, "output", "context", "player_stats.json")
REPORT = os.path.join(BASE_DIR, "output", "context", "f04_backtest_report.json")


def main():
    with open(PLAYER_STATS, encoding="utf-8") as f:
        players = json.load(f)

    checks = []
    failures = []

    def check(name, ok, detail=None):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            failures.append(name)

    kohli = players.get("V Kohli")
    check("kohli_present", kohli is not None)
    if kohli:
        check("career_preserved", kohli["batting"]["runs"] == 28134, kohli["batting"]["runs"])
        check("has_form", "form" in kohli and "last_10_innings" in kohli["form"])
        check("has_phases", bool(kohli.get("phases")))
        form = kohli["form"]
        check(
            "form_window_nesting",
            form["last_5_innings"]["balls"] <= form["last_10_innings"]["balls"]
            and form["last_5_innings"]["innings"] == 5
            and form["last_10_innings"]["innings"] == 10,
        )
        ipl = (kohli.get("phases") or {}).get("IPL") or {}
        if ipl.get("death") and ipl.get("powerplay"):
            check(
                "kohli_ipl_death_gt_powerplay",
                ipl["death"]["strike_rate"] > ipl["powerplay"]["strike_rate"],
                {
                    "death": ipl["death"]["strike_rate"],
                    "powerplay": ipl["powerplay"]["strike_rate"],
                },
            )

    enriched = 0
    reliable_phase_players = 0
    reliable_venue_blocks = 0
    for entry in players.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("form"):
            enriched += 1
        if any(
            player_phase_is_reliable(block)
            for phases in (entry.get("phases") or {}).values()
            for block in phases.values()
        ):
            reliable_phase_players += 1
        for block in (entry.get("venues") or {}).values():
            if player_venue_is_reliable(block):
                reliable_venue_blocks += 1

    check("enriched_players_gt_1000", enriched > 1000, enriched)
    check("reliable_phase_players_gt_500", reliable_phase_players > 500, reliable_phase_players)
    check("reliable_venue_blocks_gt_500", reliable_venue_blocks > 500, reliable_venue_blocks)

    engine = InsightEngine(player_stats=players)
    if kohli:
        phase_hit = engine.player_phase_mismatch("V Kohli", "IPL", "death", 40, 15)
        check("kohli_phase_mismatch_fires", phase_hit is not None, (phase_hit or {}).get("headline"))
        # thin venue must refuse
        thin_stats = {
            "V Kohli": {
                **kohli,
                "venues": {
                    "Tiny Ground": {
                        "batting": {
                            "innings": 2, "runs": 10, "balls": 20, "strike_rate": 50,
                            "fours": 0, "sixes": 0, "dismissals": 1, "average": 10,
                        },
                        "bowling": {},
                    }
                },
            }
        }
        thin_engine = InsightEngine(player_stats=thin_stats, venue_stats={})
        check(
            "thin_venue_refused",
            thin_engine.venue_form_convergence("V Kohli", "Tiny Ground", 50, 20) is None,
        )

    report = {
        "player_count": len(players),
        "enriched_players": enriched,
        "reliable_phase_players": reliable_phase_players,
        "reliable_venue_blocks": reliable_venue_blocks,
        "checks": checks,
        "failed": failures,
        "passed": len(failures) == 0,
    }
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(f"F04 backtest FAILED: {failures}")
    print("F04 backtest PASSED")


if __name__ == "__main__":
    main()
