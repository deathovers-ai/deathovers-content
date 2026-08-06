"""
F11 backtest — phase windows for ODI / The Hundred.

Isolation rule: T20/ODI stay over-based; Hundred is ball-native
(ECB 25-ball PP). Never infer Hundred from "20 overs" alone.
T10 is deferred (not in phase tables / live maps).

ODI: empirical check on venue_stats phase rates (death RR ≥ middle).
Hundred: structural + synthetic ball→phase (no HND venue corpus yet).

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
    PHASE_BOUNDARIES_BALLS,
    balls_per_over_for_match_type,
    determine_phase_from_balls,
    determine_phase_from_over,
    format_total_overs,
    innings_legal_balls,
    is_ball_native_format,
    is_experimental_format,
    phase_bounds_balls,
    phase_bounds_list,
    phase_kind_for_match_type,
    phase_set_for_total_overs,
)
from match_intelligence_api import determine_phase, map_format

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENUE_STATS = os.path.join(BASE_DIR, "output", "context", "venue_stats.json")
PHASE_DISTS = os.path.join(BASE_DIR, "output", "context", "phase_distributions.json")
CHASE_INDEX = os.path.join(BASE_DIR, "output", "compact_chase_index.json.gz")
REPORT = os.path.join(BASE_DIR, "output", "context", "f11_backtest_report.json")

MIN_ODI_VENUE_N = 10
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

    # --- Isolation: over table vs ball table --------------------------
    check("hundred_not_in_over_table", "HUNDRED" not in PHASE_BOUNDARIES)
    check("t10_not_in_over_table", "T10_LIKE" not in PHASE_BOUNDARIES)
    check("t20_still_in_over_table", PHASE_BOUNDARIES["T20_LIKE"]["powerplay"] == (0, 6))
    check("odi_still_in_over_table", PHASE_BOUNDARIES["ODI_LIKE"]["death"] == (40, 50))
    check(
        "hundred_ball_pp_25",
        PHASE_BOUNDARIES_BALLS["HUNDRED"]["powerplay"] == (0, 25),
    )
    check(
        "hundred_ball_death_last_25",
        PHASE_BOUNDARIES_BALLS["HUNDRED"]["death"] == (75, 100),
    )
    check("hundred_ball_native", is_ball_native_format("HUNDRED") is True)
    check("t20_not_ball_native", is_ball_native_format("T20") is False)
    check("odi_not_ball_native", is_ball_native_format("ODI") is False)

    check(
        "twenty_overs_is_t20_not_hundred",
        phase_set_for_total_overs(20) is PHASE_BOUNDARIES["T20_LIKE"],
    )
    check(
        "ten_overs_is_t20_not_t10",
        phase_set_for_total_overs(10) is PHASE_BOUNDARIES["T20_LIKE"],
    )

    check("hundred_balls_per_over", balls_per_over_for_match_type("HUNDRED") == 5)
    check("t20_balls_per_over", balls_per_over_for_match_type("T20") == 6)
    check("odi_balls_per_over", balls_per_over_for_match_type("ODI") == 6)
    check("hundred_legal_balls", innings_legal_balls("HND") == 100)
    check("odi_not_experimental", is_experimental_format("ODI") is False)
    check("format_total_odi", format_total_overs("ODI") == 50)
    check("t10_deferred_maps_t20_like", phase_kind_for_match_type("T10") == "T20_LIKE")
    check("t10_not_in_live_map", map_format("T10") is None)

    for code, kind in (
        ("ODI", "ODI_LIKE"),
        ("ODM", "ODI_LIKE"),
        ("HND", "HUNDRED"),
        ("100", "HUNDRED"),
        ("HUNDRED", "HUNDRED"),
        ("T20", "T20_LIKE"),
        ("IPL", "T20_LIKE"),
    ):
        check(f"kind_{code}", phase_kind_for_match_type(code) == kind, phase_kind_for_match_type(code))

    for feed, expected in (
        ("ODI", "ODI"),
        ("Hundred", "HUNDRED"),
        ("100", "HUNDRED"),
        ("HND", "HUNDRED"),
        ("T20I", "T20"),
    ):
        check(f"map_{feed}", map_format(feed) == expected, map_format(feed))

    for over, fmt, want in (
        (9, "ODI", "powerplay"),
        (10, "ODI", "middle"),
        (39, "ODI", "middle"),
        (40, "ODI", "death"),
        (5, "T20", "powerplay"),
        (6, "T20", "middle"),
        (15, "T20", "death"),
    ):
        got = determine_phase(over, fmt)
        check(f"edge_{fmt}_{over}", got == want, got)

    for ball, want in (
        (0, "powerplay"),
        (24, "powerplay"),
        (25, "middle"),
        (74, "middle"),
        (75, "death"),
        (99, "death"),
    ):
        got = determine_phase_from_balls(ball, "HUNDRED")
        check(f"hundred_ball_{ball}", got == want, got)

    check(
        "odi_vs_t20_over8",
        determine_phase(8, "ODI") == "powerplay" and determine_phase(8, "T20") == "middle",
    )
    check(
        "hundred_vs_t20_ball25",
        determine_phase_from_balls(25, "HUNDRED") == "middle"
        and determine_phase(5, "T20") == "powerplay",
    )
    check("t20_ball_bounds_36", phase_bounds_balls("T20")[0] == ("powerplay", 0, 36))
    check("hundred_ball_bounds_25", phase_bounds_balls("HUNDRED")[0] == ("powerplay", 0, 25))

    hundred_ok = True
    for ball in range(100):
        phase = determine_phase_from_balls(ball, "HUNDRED")
        want = "powerplay" if ball < 25 else ("middle" if ball < 75 else "death")
        if phase != want:
            hundred_ok = False
            check("hundred_ball_map", False, {"ball": ball, "got": phase, "want": want})
            break
    if hundred_ok:
        check("hundred_ball_map", True, {"balls": 100, "pp_balls": 25, "death_balls": 25})

    adapter_ok = True
    for over in range(20):
        from_over = determine_phase_from_over(over, "HUNDRED")
        from_ball = determine_phase_from_balls(over * 5, "HUNDRED")
        if from_over != from_ball:
            adapter_ok = False
            check(
                "hundred_adapter_agrees",
                False,
                {"over": over, "from_over": from_over, "from_ball": from_ball},
            )
            break
    if adapter_ok:
        check("hundred_adapter_agrees", True)

    for fmt in ("ODI", "T20"):
        total = format_total_overs(fmt)
        phases_hit = {determine_phase_from_over(o, fmt) for o in range(total)}
        check(f"cover_{fmt}", phases_hit == {"powerplay", "middle", "death"}, sorted(phases_hit))
        bounds = phase_bounds_list(fmt)
        check(
            f"contig_{fmt}",
            bounds[0][1] == 0
            and bounds[-1][2] == total
            and all(bounds[i][2] == bounds[i + 1][1] for i in range(len(bounds) - 1)),
            bounds,
        )

    phases_hit = {determine_phase_from_balls(b, "HUNDRED") for b in range(100)}
    check("cover_HUNDRED", phases_hit == {"powerplay", "middle", "death"}, sorted(phases_hit))
    hb = phase_bounds_balls("HUNDRED")
    check(
        "contig_HUNDRED_balls",
        hb[0][1] == 0
        and hb[-1][2] == 100
        and all(hb[i][2] == hb[i + 1][1] for i in range(len(hb) - 1)),
        hb,
    )

    odi_report = {
        "venues_ge_n": 0,
        "death_ge_mid": 0,
        "skipped_no_corpus_hundred": True,
        "t10_deferred": True,
    }
    if os.path.exists(VENUE_STATS):
        with open(VENUE_STATS, encoding="utf-8") as f:
            venues = json.load(f)
        rows = []
        t20_rows = []
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
            t20 = (meta.get("formats") or {}).get("T20") or {}
            if (t20.get("matches_with_data") or 0) >= MIN_ODI_VENUE_N:
                pb = t20.get("phase_breakdown") or {}
                mid = (pb.get("middle") or {}).get("avg_run_rate")
                death = (pb.get("death") or {}).get("avg_run_rate")
                if mid is not None and death is not None:
                    t20_rows.append(death >= mid)
        odi_report["venues_ge_n"] = len(rows)
        death_ge = sum(1 for r in rows if r["death"] >= r["mid"])
        odi_report["death_ge_mid"] = death_ge
        frac = (death_ge / len(rows)) if rows else 0.0
        odi_report["death_ge_mid_frac"] = round(frac, 4)
        check("odi_venues_present", len(rows) >= 30, len(rows))
        check(
            "odi_death_rr_ge_middle",
            frac >= MIN_ODI_DEATH_GE_MID_FRAC,
            {"frac": round(frac, 4), "death_ge_mid": death_ge, "n": len(rows)},
        )
        if t20_rows:
            t20_frac = sum(t20_rows) / len(t20_rows)
            odi_report["t20_death_ge_mid_frac"] = round(t20_frac, 4)
            check(
                "t20_death_rr_ge_middle_regression",
                t20_frac >= 0.85,
                {"frac": round(t20_frac, 4), "n": len(t20_rows)},
            )
        fmt_keys = set()
        for meta in venues.values():
            if isinstance(meta, dict):
                fmt_keys.update((meta.get("formats") or {}).keys())
        check("corpus_has_odi", "ODI" in fmt_keys, sorted(fmt_keys))
        check("corpus_has_t20", "T20" in fmt_keys)
        check("corpus_lacks_hundred", "HND" not in fmt_keys and "HUNDRED" not in fmt_keys)
    else:
        check("venue_stats_present", False, VENUE_STATS)

    if os.path.exists(PHASE_DISTS):
        with open(PHASE_DISTS, encoding="utf-8") as f:
            dists = json.load(f)
        formats = dists.get("formats") or {}
        for fmt in ("ODI", "T20"):
            block = formats.get(fmt) or {}
            for phase in ("powerplay", "middle", "death"):
                n = (block.get(phase) or {}).get("n") or 0
                check(f"{fmt}_dist_{phase}_n", n >= 30, n)
            mid_m = (block.get("middle") or {}).get("runs_per_over_mean")
            death_m = (block.get("death") or {}).get("runs_per_over_mean")
            check(
                f"{fmt}_dist_death_gt_middle",
                mid_m is not None and death_m is not None and death_m > mid_m,
                {"middle": mid_m, "death": death_m},
            )
        check("dists_lack_hundred", "HUNDRED" not in formats and "HND" not in formats)
        check("dists_lack_t10", "T10" not in formats and "T10_LIKE" not in formats)
    else:
        check("phase_dists_present", False, PHASE_DISTS)

    if os.path.exists(CHASE_INDEX):
        with gzip.open(CHASE_INDEX, "rt", encoding="utf-8") as f:
            index = json.load(f)
        buckets = index.get("buckets") or {}
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
        "windows_overs": {
            kind: {name: list(bounds) for name, bounds in phases.items()}
            for kind, phases in PHASE_BOUNDARIES.items()
        },
        "windows_balls": {
            kind: {name: list(bounds) for name, bounds in phases.items()}
            for kind, phases in PHASE_BOUNDARIES_BALLS.items()
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
