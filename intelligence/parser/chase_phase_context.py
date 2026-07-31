"""
Phase Builder — Chase phase context (one module, one job).

Locked product rules (do not invent beyond these):
  1. Leave existing venue_stats phase_breakdown alone (1st-innings historical).
  2. Write a SEPARATE key: chase_phase_breakdown.
  3. Successful chases only (2nd innings batting team == match winner).
  4. Per-phase run_pct_of_target = mean(phase_runs / target) * 100
     where target = 1st-innings final runs + 1.
  5. Exclude matches with outcome.method set (e.g. D/L).

Run AFTER context_repository.py so venue_stats.json already exists:
  python context_repository.py
  python chase_phase_context.py

Reads:  output/events/*.json, output/manifest.json, output/context/venue_stats.json
Writes: output/context/venue_stats.json (adds chase_phase_breakdown only)
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_repository import (
    LIMITED_OVERS_FORMATS,
    format_total_overs,
    normalize_venue,
    phase_set_for_format,
)
from metrics_engine import current_run_rate
from replay_engine import ReplayEngine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_DIR = os.path.join(BASE_DIR, "output", "events")
MANIFEST = os.path.join(BASE_DIR, "output", "manifest.json")
VENUE_STATS_FILE = os.path.join(BASE_DIR, "output", "context", "venue_stats.json")


def _is_interrupted_method(outcome):
    """True when Cricsheet flags a non-standard result method (D/L, etc.)."""
    method = (outcome or {}).get("method")
    return bool(method)


def _phase_bucket_innings(events, phases):
    """Bucket one match's events into per-innings phase runs/balls + totals."""
    innings_data = {}
    for event in events:
        n = event["innings_num"]
        if n not in innings_data:
            innings_data[n] = {
                "runs": 0,
                "wickets": 0,
                "phase_runs": {p: 0 for p in phases},
                "phase_balls": {p: 0 for p in phases},
                "batting_team": event["batting_team"],
            }
        d = innings_data[n]
        d["runs"] += event["runs_total"]
        if event["is_wicket"]:
            d["wickets"] += len(event["wickets"])
        if event["is_legal_delivery"]:
            over = event["over"]
            for phase_name, (start, end) in phases.items():
                if start <= over < end:
                    d["phase_runs"][phase_name] += event["runs_total"]
                    d["phase_balls"][phase_name] += 1
                    break
    return innings_data


def aggregate_chase_phase_sample(phase_rows_by_phase, targets):
    """
    Pure aggregation for one venue+format sample list.

    phase_rows_by_phase: {phase: [{"runs": int, "balls": int}, ...]}
    targets: [int, ...] aligned 1:1 with each chase in the sample
             (same length as each phase list)

    Returns dict shaped for chase_phase_breakdown, or None if empty.
    """
    n = len(targets)
    if n == 0:
        return None

    phases_out = {}
    for phase_name, rows in phase_rows_by_phase.items():
        if len(rows) != n:
            raise ValueError(
                f"phase {phase_name} row count {len(rows)} != target count {n}"
            )
        total_runs = sum(r["runs"] for r in rows)
        total_balls = sum(r["balls"] for r in rows)
        pcts = [
            (rows[i]["runs"] / targets[i]) * 100
            for i in range(n)
            if targets[i] > 0
        ]
        phases_out[phase_name] = {
            "avg_runs": round(total_runs / n, 1),
            "avg_run_rate": current_run_rate(total_runs, total_balls),
            "run_pct_of_target": round(sum(pcts) / len(pcts), 1) if pcts else None,
        }

    return {
        "successful_chase_sample_size": n,
        "avg_target": round(sum(targets) / n, 1),
        "phases": phases_out,
    }


def collect_successful_chase_phases():
    """
    Scan limited-overs events; return
      {venue_key: {match_type: {"targets": [...], "phases": {phase: [rows...]}}}}
    """
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)

    limited = [m for m in manifest if m["competition_code"] in LIMITED_OVERS_FORMATS]
    print(f"Scanning {len(limited)} limited-overs matches for successful-chase phases...")

    # venue -> format -> phase -> list of {runs, balls}; plus targets list
    accum_phases = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    accum_targets = defaultdict(lambda: defaultdict(list))

    processed = 0
    kept = 0
    skipped_dl = 0
    skipped_other = 0

    for m in limited:
        match_id = m["match_id"]
        path = os.path.join(EVENTS_DIR, f"{match_id}.json")
        if not os.path.exists(path):
            skipped_other += 1
            continue

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        meta = data["meta"]
        outcome = meta.get("outcome") or {}

        if _is_interrupted_method(outcome):
            skipped_dl += 1
            continue

        winner = outcome.get("winner")
        if not winner:
            skipped_other += 1
            continue

        raw_venue = meta.get("venue")
        if not raw_venue:
            skipped_other += 1
            continue

        match_type = m["competition_code"]
        total_overs = format_total_overs(match_type)
        phases = phase_set_for_format(total_overs)

        try:
            engine = ReplayEngine(match_id)
            innings_data = _phase_bucket_innings(engine.all_events, phases)
        except Exception:
            skipped_other += 1
            continue

        first = innings_data.get(1)
        second = innings_data.get(2)
        if not first or not second:
            skipped_other += 1
            continue

        if second["batting_team"] != winner:
            # failed chase / bat-first win — out of scope for this module
            processed += 1
            continue

        target = first["runs"] + 1
        if target <= 0:
            skipped_other += 1
            continue

        venue_key = normalize_venue(raw_venue)
        accum_targets[venue_key][match_type].append(target)
        for phase_name in phases:
            accum_phases[venue_key][match_type][phase_name].append({
                "runs": second["phase_runs"][phase_name],
                "balls": second["phase_balls"][phase_name],
            })
        kept += 1
        processed += 1
        if processed % 3000 == 0:
            print(f"  {processed}/{len(limited)} scanned (kept successful chases: {kept})")

    print(
        f"Done. successful chases kept={kept}, "
        f"skipped_method(D/L etc)={skipped_dl}, skipped_other={skipped_other}"
    )
    return accum_phases, accum_targets


def build_chase_phase_by_venue(accum_phases, accum_targets):
    """Turn raw accumulators into {venue: {format: chase_phase_breakdown}}."""
    out = {}
    for venue_key, by_format in accum_targets.items():
        out.setdefault(venue_key, {})
        for match_type, targets in by_format.items():
            phase_rows = accum_phases[venue_key][match_type]
            breakdown = aggregate_chase_phase_sample(phase_rows, targets)
            if breakdown:
                out[venue_key][match_type] = breakdown
    return out


def merge_chase_phases_into_venue_stats(venue_stats, chase_by_venue):
    """
    Attach chase_phase_breakdown under each existing venue/format.
    Does not create new venues. Does not modify phase_breakdown.
    Removes stale chase_phase_breakdown when this rebuild has no sample.
    """
    attached = 0
    cleared = 0
    for venue_key, entry in venue_stats.items():
        formats = entry.get("formats") or {}
        chase_formats = chase_by_venue.get(venue_key) or {}
        for match_type, fmt in formats.items():
            if match_type in chase_formats:
                fmt["chase_phase_breakdown"] = chase_formats[match_type]
                attached += 1
            elif "chase_phase_breakdown" in fmt:
                del fmt["chase_phase_breakdown"]
                cleared += 1
    return attached, cleared


def rebuild_chase_phase_context():
    if not os.path.exists(VENUE_STATS_FILE):
        raise FileNotFoundError(
            f"{VENUE_STATS_FILE} missing — run context_repository.py first."
        )
    if not os.path.exists(MANIFEST):
        raise FileNotFoundError(f"{MANIFEST} missing — run build_manifest.py first.")

    accum_phases, accum_targets = collect_successful_chase_phases()
    chase_by_venue = build_chase_phase_by_venue(accum_phases, accum_targets)

    with open(VENUE_STATS_FILE, encoding="utf-8") as f:
        venue_stats = json.load(f)

    attached, cleared = merge_chase_phases_into_venue_stats(venue_stats, chase_by_venue)

    with open(VENUE_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(venue_stats, f, indent=2)

    print(
        f"Updated {VENUE_STATS_FILE}: "
        f"attached chase_phase_breakdown to {attached} venue/format blocks "
        f"(cleared stale: {cleared})"
    )
    return venue_stats


def _self_check():
    """Smallest check that fails if aggregation math breaks. No fixtures."""
    # Two successful chases, target 100 and 200.
    # PP runs 30 and 50 -> avg_runs 40, pcts 30% and 25% -> mean 27.5
    phase_rows = {
        "powerplay": [{"runs": 30, "balls": 36}, {"runs": 50, "balls": 36}],
        "middle": [{"runs": 40, "balls": 54}, {"runs": 80, "balls": 54}],
        "death": [{"runs": 35, "balls": 30}, {"runs": 70, "balls": 30}],
    }
    targets = [100, 200]
    out = aggregate_chase_phase_sample(phase_rows, targets)
    assert out["successful_chase_sample_size"] == 2
    assert out["avg_target"] == 150.0
    assert out["phases"]["powerplay"]["avg_runs"] == 40.0
    assert out["phases"]["powerplay"]["run_pct_of_target"] == 27.5
    assert out["phases"]["middle"]["run_pct_of_target"] == 40.0
    assert out["phases"]["death"]["run_pct_of_target"] == 35.0
    # run rate: (30+50)/(36+36)*6 = 80/72*6 = 6.67
    assert out["phases"]["powerplay"]["avg_run_rate"] == 6.67

    # merge must not touch phase_breakdown
    vs = {
        "Test Ground": {
            "formats": {
                "T20": {
                    "phase_breakdown": {"powerplay": {"avg_runs": 45.0}},
                    "matches_with_data": 10,
                }
            }
        }
    }
    chase = {
        "Test Ground": {
            "T20": out,
        }
    }
    merge_chase_phases_into_venue_stats(vs, chase)
    assert vs["Test Ground"]["formats"]["T20"]["phase_breakdown"]["powerplay"]["avg_runs"] == 45.0
    assert "chase_phase_breakdown" in vs["Test Ground"]["formats"]["T20"]
    assert _is_interrupted_method({"method": "D/L", "winner": "A"}) is True
    assert _is_interrupted_method({"winner": "A"}) is False
    print("chase_phase_context self-check OK")


if __name__ == "__main__":
    _self_check()
    if os.path.exists(EVENTS_DIR) and os.path.exists(MANIFEST) and os.path.exists(VENUE_STATS_FILE):
        stats = rebuild_chase_phase_context()
        sample = next((k for k in stats if "Wankhede" in k), None)
        if sample:
            ipl = stats[sample]["formats"].get("IPL", {})
            print(f"\nSample: {sample} IPL chase_phase_breakdown:")
            print(json.dumps(ipl.get("chase_phase_breakdown"), indent=2))
    else:
        print(
            "Events/manifest/venue_stats not all present in this environment — "
            "self-check only. Run rebuild on the machine with the full corpus."
        )
