"""
F11 backtest — phase windows for ODI / The Hundred / T10.

ODI: empirical check on venue_stats phase rates (death RR ≥ middle).
Hundred / T10: no HND/T10 venue corpus in this deploy — structural +
synthetic ball→phase assignment (5-ball Hundred, 6-ball T10).

Usage (from intelligence/parser):
  python3 backtest_phase_formats.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import (
    PHASE_BOUNDARIES,
    balls_per_over_for_match_type,
    determine_phase_from_over,
    format_total_overs,
    innings_legal_balls,
    is_experimental_format,
    phase_bounds_list,
    phase_kind_for_match_type,
    phase_set_for_match_type,
)
from match_intelligence_api import determine_phase, map_format

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENUE_STATS = os.path.join(BASE_DIR, "output", "context", "venue_stats.json")
PHASE_DISTS = os.path.join(BASE_DIR, "output", "context", "phase_distributions.json")
CHASE_INDEX = os.path.join(BASE_DIR, "output", "compact_chase_index.json.gz")
REPORT = os.path.join(BASE_DIR, "output", "context", "f11_backtest_report.json")

MIN_ODI_VENUE_N = 10
# Death should be at least as fast as middle at most ODI grounds.
MIN_ODI_DEATH_GE_MID_FRAC = 0.90


def main():
    checks = []
    failures = []

    def check(name, ok, detail=None):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        status = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail is not None else ""
        print(f"[{status}] {name}{extra}")
        if not ok:
            failures.append(name)

    # --- Contract: windows + routing ---------------------------------
    check("odi_pp", PHASE_BOUNDARIES["ODI_LIKE"]["powerplay"] == (0, 10))
    check("odi_death", PHASE_BOUNDARIES["ODI_LIKE"]["death"] == (40, 50))
    check("hundred_pp_25_balls", PHASE_BOUNDARIES["HUNDRED"]["powerplay"] == (0, 5))
    check("hundred_balls_per_over", balls_per_over_for_match_type("HUNDRED") == 5)
    check("hundred_legal_balls", innings_legal_balls("HND") == 100)
    check("t10_pp", PHASE_BOUNDARIES["T10_LIKE"]["powerplay"] == (0, 3))
    check("t10_death", PHASE_BOUNDARIES["T10_LIKE"]["death"] == (7, 10))
    check("t10_experimental", is_experimental_format("T10") is True)
    check("odi_not_experimental", is_experimental_format("ODI") is False)
    check("format_total_odi", format_total_overs("ODI") == 50)
    check("format_total_t10", format_total_overs("T10") == 10)
    check("format_total_hundred", format_total_overs("HUNDRED") == 20)

    for code, kind in (
        ("ODI", "ODI_LIKE"),
        ("ODM", "ODI_LIKE"),
        ("HND", "HUNDRED"),
        ("100", "HUNDRED"),
        ("HUNDRED", "HUNDRED"),
        ("T10", "T10_LIKE"),
        ("T20", "T20_LIKE"),
        ("IPL", "T20_LIKE"),
    ):
        check(f"kind_{code}", phase_kind_for_match_type(code) == kind, phase_kind_for_match_type(code))

    for feed, expected in (
        ("ODI", "ODI"),
        ("T10", "T10"),
        ("Hundred", "HUNDRED"),
        ("100", "HUNDRED"),
        ("HND", "HUNDRED"),
    ):
        check(f"map_{feed}", map_format(feed) == expected, map_format(feed))

    # Boundary edges (half-open)
    edges = [
        (9, "ODI", "powerplay"),
        (10, "ODI", "middle"),
        (39, "ODI", "middle"),
        (40, "ODI", "death"),
        (4, "HUNDRED", "powerplay"),
        (5, "HUNDRED", "middle"),
        (14, "HND", "middle"),
        (15, "HND", "death"),
        (2, "T10", "powerplay"),
        (3, "T10", "middle"),
        (6, "T10", "middle"),
        (7, "T10", "death"),
    ]
    for over, fmt, want in edges:
        got = determine_phase(over, fmt)
        check(f"edge_{fmt}_{over}", got == want, got)

    # Format routing matters: over 8 is still ODI powerplay, T20 middle.
    check(
        "odi_vs_t20_over8",
        determine_phase(8, "ODI") == "powerplay"
        and determine_phase(8, "T20") == "middle",
    )
    # Over 4: Hundred still PP, T20 still PP; over 5: Hundred middle, T20 PP.
    check(
        "hundred_vs_t20_over5",
        determine_phase(5, "HUNDRED") == "middle"
        and determine_phase(5, "T20") == "powerplay",
    )

    # --- Synthetic ball→phase (Hundred 5-ball, T10 6-ball) ------------
    hundred_ok = True
    for ball in range(100):
        over = ball // 5
        phase = determine_phase_from_over(over, "HUNDRED")
        if ball < 25:
            want = "powerplay"
        elif ball < 75:
            want = "middle"
        else:
            want = "death"
        if phase != want:
            hundred_ok = False
            check("hundred_ball_map", False, {"ball": ball, "over": over, "got": phase, "want": want})
            break
    if hundred_ok:
        check("hundred_ball_map", True, {"balls": 100, "bpo": 5, "pp_balls": 25})

    t10_ok = True
    for ball in range(60):
        over = ball // 6
        phase = determine_phase_from_over(over, "T10")
        if ball < 18:
            want = "powerplay"
        elif ball < 42:
            want = "middle"
        else:
            want = "death"
        if phase != want:
            t10_ok = False
            check("t10_ball_map", False, {"ball": ball, "over": over, "got": phase, "want": want})
            break
    if t10_ok:
        check("t10_ball_map", True, {"balls": 60, "bpo": 6, "pp_balls": 18})

    # Cover every legal over once for each format.
    for fmt in ("ODI", "HUNDRED", "T10"):
        total = format_total_overs(fmt)
        phases_hit = {determine_phase_from_over(o, fmt) for o in range(total)}
        check(
            f"cover_{fmt}",
            phases_hit == {"powerplay", "middle", "death"},
            sorted(phases_hit),
        )
        # Bounds contiguous and cover [0, total)
        bounds = phase_bounds_list(fmt)
        check(f"contig_start_{fmt}", bounds[0][1] == 0)
        check(f"contig_end_{fmt}", bounds[-1][2] == total)
        ok_contig = all(bounds[i][2] == bounds[i + 1][1] for i in range(len(bounds) - 1))
        check(f"contig_{fmt}", ok_contig, bounds)

    # --- ODI empirical: venue phase rates ------------------------------
    odi_report = {"venues_ge_n": 0, "death_ge_mid": 0, "skipped_no_corpus_hundred": True, "skipped_no_corpus_t10": True}
    if os.path.exists(VENUE_STATS):
        with open(VENUE_STATS, encoding="utf-8") as f:
            venues = json.load(f)
        rows = []
        for venue_key, meta in venues.items():
            if not isinstance(meta, dict):
                continue
            for fmt in ("ODI", "ODM"):
                block = (meta.get("formats") or {}).get(fmt) or {}
                n = block.get("matches_with_data") or 0
                if n < MIN_ODI_VENUE_N:
                    continue
                pb = block.get("phase_breakdown") or {}
                mid = (pb.get("middle") or {}).get("avg_run_rate")
                death = (pb.get("death") or {}).get("avg_run_rate")
                if mid is None or death is None:
                    continue
                rows.append({"venue": venue_key, "format": fmt, "n": n, "mid": mid, "death": death})
        odi_report["venues_ge_n"] = len(rows)
        death_ge = sum(1 for r in rows if r["death"] >= r["mid"])
        odi_report["death_ge_mid"] = death_ge
        frac = (death_ge / len(rows)) if rows else 0.0
        odi_report["death_ge_mid_frac"] = round(frac, 4)
        check(
            "odi_venues_present",
            len(rows) >= 30,
            len(rows),
        )
        check(
            "odi_death_rr_ge_middle",
            frac >= MIN_ODI_DEATH_GE_MID_FRAC,
            {"frac": round(frac, 4), "death_ge_mid": death_ge, "n": len(rows)},
        )
        # Corpus has no Hundred / T10 format keys yet — document, don't invent.
        fmt_keys = set()
        for meta in venues.values():
            if isinstance(meta, dict):
                fmt_keys.update((meta.get("formats") or {}).keys())
        check("corpus_has_odi", "ODI" in fmt_keys, sorted(fmt_keys))
        check("corpus_lacks_hundred", "HND" not in fmt_keys and "HUNDRED" not in fmt_keys)
        check("corpus_lacks_t10", "T10" not in fmt_keys)
    else:
        check("venue_stats_present", False, VENUE_STATS)

    # Phase distributions publish ODI death/middle/PP blocks.
    if os.path.exists(PHASE_DISTS):
        with open(PHASE_DISTS, encoding="utf-8") as f:
            dists = json.load(f)
        odi = (dists.get("formats") or {}).get("ODI") or {}
        for phase in ("powerplay", "middle", "death"):
            n = (odi.get(phase) or {}).get("n") or 0
            check(f"odi_dist_{phase}_n", n >= 50, n)
        # Death mean RR should beat middle at format aggregate.
        mid_m = (odi.get("middle") or {}).get("runs_per_over_mean")
        death_m = (odi.get("death") or {}).get("runs_per_over_mean")
        check(
            "odi_dist_death_gt_middle",
            mid_m is not None and death_m is not None and death_m > mid_m,
            {"middle": mid_m, "death": death_m},
        )
    else:
        check("phase_dists_present", False, PHASE_DISTS)

    # Compact chase index: ODI legal_balls at phase edges map correctly.
    if os.path.exists(CHASE_INDEX):
        with gzip.open(CHASE_INDEX, "rt", encoding="utf-8") as f:
            index = json.load(f)
        buckets = index.get("buckets") or {}
        # Format-global ODI cells at PP→middle (60 balls) and middle→death (240).
        edge_balls = {
            "pp_end": (10 * 6, "middle"),
            "death_start": (40 * 6, "death"),
        }
        found = {label: 0 for label in edge_balls}
        for key in buckets:
            parts = key.split("|")
            if len(parts) != 5 or parts[0] != "ODI" or parts[1] != "*":
                continue
            try:
                balls = int(parts[2])
            except ValueError:
                continue
            for label, (want_balls, _expect) in edge_balls.items():
                if balls == want_balls:
                    found[label] += 1
        for label, (want_balls, expect) in edge_balls.items():
            phase = determine_phase_from_over(want_balls / 6, "ODI")
            check(f"chase_edge_{label}_phase", phase == expect, {"balls": want_balls, "phase": phase})
            check(f"chase_odi_{label}_present", found[label] > 0, found[label])
        odi_report["chase_edge_hits"] = found
    else:
        check("chase_index_present", False, CHASE_INDEX)

    report = {
        "windows": {
            kind: {name: list(bounds) for name, bounds in phases.items()}
            for kind, phases in PHASE_BOUNDARIES.items()
        },
        "odi_empirical": odi_report,
        "checks": checks,
        "failed": failures,
        "passed": len(failures) == 0,
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(f"Wrote {REPORT}")
    if failures:
        print(f"FAILED {len(failures)}: {failures}")
        raise SystemExit(1)
    print(f"All {len(checks)} checks passed.")


if __name__ == "__main__":
    main()
