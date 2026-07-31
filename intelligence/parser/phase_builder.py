"""Innings-aware Phase Builder for limited-overs matches.

This module is intentionally independent from newsletter and DLS features.  It
turns the parsed Cricsheet event store into two honest products:

* first innings: a historical venue benchmark; and
* second innings: target-aware phase checkpoints based on completed successful
  chases at that venue.

Interrupted/adjusted matches are excluded.  A target calculated for a phase is
always a checkpoint on the way to the match target, so the three checkpoint
allocations cannot exceed the target in aggregate.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterable

from context_repository import (
    LIMITED_OVERS_FORMATS,
    format_total_overs,
    normalize_venue,
    phase_set_for_format,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EVENTS_DIR = os.path.join(BASE_DIR, "output", "events")
DEFAULT_MANIFEST = os.path.join(BASE_DIR, "output", "manifest.json")
MIN_SAMPLE_SIZE = 8
ADJUSTED_METHODS = {"D/L", "DLS", "VJD", "Awarded", "1st innings score", "Lost fewer wickets"}


class PhaseDataError(ValueError):
    """Raised when Phase Builder cannot make a defensible comparison."""


@dataclass(frozen=True)
class PhaseSummary:
    runs: int
    wickets: int
    legal_balls: int

    @property
    def run_rate(self) -> float:
        return round((self.runs * 6 / self.legal_balls), 2) if self.legal_balls else 0.0


def _is_adjusted(meta: dict[str, Any]) -> bool:
    outcome = meta.get("outcome") or {}
    return outcome.get("method") in ADJUSTED_METHODS


def _empty_phase_summaries(match_type: str) -> dict[str, dict[str, int]]:
    return {name: {"runs": 0, "wickets": 0, "legal_balls": 0}
            for name in phase_set_for_format(format_total_overs(match_type))}


def summarize_innings(events: Iterable[dict[str, Any]], innings_num: int, match_type: str) -> dict[str, PhaseSummary]:
    """Count every delivery's runs and wickets in its phase; balls are legal only."""
    phases = phase_set_for_format(format_total_overs(match_type))
    totals = _empty_phase_summaries(match_type)
    for event in events:
        if event.get("innings_num") != innings_num:
            continue
        for phase, (start, end) in phases.items():
            if start <= event["over"] < end:
                totals[phase]["runs"] += int(event.get("runs_total", 0))
                totals[phase]["wickets"] += len(event.get("wickets") or [])
                if event.get("is_legal_delivery"):
                    totals[phase]["legal_balls"] += 1
                break
    return {name: PhaseSummary(**values) for name, values in totals.items()}


def _innings_total(events: Iterable[dict[str, Any]], innings_num: int) -> int:
    return sum(int(e.get("runs_total", 0)) for e in events if e.get("innings_num") == innings_num)


def _load_match(events_dir: str, match_id: str) -> dict[str, Any]:
    path = os.path.join(events_dir, f"{match_id}.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class PhaseBuilder:
    def __init__(self, events_dir: str = DEFAULT_EVENTS_DIR, manifest_path: str = DEFAULT_MANIFEST,
                 min_sample_size: int = MIN_SAMPLE_SIZE):
        self.events_dir = events_dir
        self.min_sample_size = min_sample_size
        with open(manifest_path, encoding="utf-8") as handle:
            self.manifest = json.load(handle)

    def _historical_matches(self, venue: str, match_type: str, exclude_match_id: str | None = None):
        venue_key = normalize_venue(venue)
        for item in self.manifest:
            if item.get("competition_code") != match_type or item.get("match_id") == exclude_match_id:
                continue
            path = os.path.join(self.events_dir, f"{item['match_id']}.json")
            if not os.path.exists(path):
                continue
            data = _load_match(self.events_dir, item["match_id"])
            meta = data.get("meta", {})
            if _is_adjusted(meta) or normalize_venue(meta.get("venue", "")) != venue_key:
                continue
            yield data

    def venue_benchmarks(self, venue: str, match_type: str, exclude_match_id: str | None = None) -> dict[str, Any]:
        if match_type not in LIMITED_OVERS_FORMATS:
            raise PhaseDataError("Phase Builder supports limited-overs formats only.")
        summaries = []
        for data in self._historical_matches(venue, match_type, exclude_match_id):
            summaries.append(summarize_innings(data["events"], 1, match_type))
        if len(summaries) < self.min_sample_size:
            raise PhaseDataError(f"Insufficient normal-match sample at {venue}: {len(summaries)} (need {self.min_sample_size}).")
        result: dict[str, Any] = {"venue": venue, "format": match_type, "sample_size": len(summaries), "phases": {}}
        for phase in summaries[0]:
            result["phases"][phase] = {
                "avg_runs": round(sum(s[phase].runs for s in summaries) / len(summaries), 1),
                "avg_wickets": round(sum(s[phase].wickets for s in summaries) / len(summaries), 1),
                "avg_run_rate": round(sum(s[phase].run_rate for s in summaries) / len(summaries), 2),
            }
        return result

    def successful_chase_distribution(self, venue: str, match_type: str,
                                      exclude_match_id: str | None = None) -> dict[str, Any]:
        """Return checkpoint shares from normal successful chases only."""
        chases: list[tuple[int, dict[str, PhaseSummary]]] = []
        for data in self._historical_matches(venue, match_type, exclude_match_id):
            events, meta = data["events"], data["meta"]
            if not events or not (meta.get("outcome") or {}).get("winner"):
                continue
            innings_two = [e for e in events if e.get("innings_num") == 2]
            if not innings_two:
                continue
            batting_team = innings_two[0].get("batting_team")
            if batting_team != meta["outcome"].get("winner"):
                continue
            target = _innings_total(events, 1) + 1
            if _innings_total(events, 2) < target:
                continue
            chases.append((target, summarize_innings(events, 2, match_type)))
        if len(chases) < self.min_sample_size:
            raise PhaseDataError(f"Insufficient successful-chase sample at {venue}: {len(chases)} (need {self.min_sample_size}).")
        # These are cumulative checkpoints, not independent shares.  This prevents
        # a UI from presenting impossible targets whose phase totals exceed target.
        phase_names = list(chases[0][1])
        cumulative = []
        running = {p: 0 for p in phase_names}
        for target, summary in chases:
            for phase in phase_names:
                running[phase] += summary[phase].runs
                cumulative.append((phase, min(running[phase] / target, 1.0)))
                running[phase] = 0
        raw_share = {p: round(sum(value for name, value in cumulative if name == p) / len(chases), 4) for p in phase_names}
        total = sum(raw_share.values())
        shares = {p: round(raw_share[p] / total, 4) for p in phase_names}
        # Last phase absorbs rounding so the returned shares sum exactly to 1.
        shares[phase_names[-1]] = round(1 - sum(shares[p] for p in phase_names[:-1]), 4)
        return {"venue": venue, "format": match_type, "sample_size": len(chases), "phase_shares": shares}

    def analyze_match(self, match_id: str) -> dict[str, Any]:
        data = _load_match(self.events_dir, match_id)
        meta, events = data["meta"], data["events"]
        if _is_adjusted(meta):
            raise PhaseDataError("Adjusted/rain-affected matches are excluded from Phase Builder.")
        match_type, venue = meta.get("competition_code"), meta.get("venue")
        if match_type not in LIMITED_OVERS_FORMATS or not venue:
            raise PhaseDataError("Match is not an eligible limited-overs venue match.")
        first = summarize_innings(events, 1, match_type)
        benchmark = self.venue_benchmarks(venue, match_type, exclude_match_id=match_id)
        first_report = self._first_innings_report(first, benchmark)
        second_events = [e for e in events if e.get("innings_num") == 2]
        report: dict[str, Any] = {"match_id": match_id, "venue": venue, "format": match_type, "first_innings": first_report}
        if second_events:
            target = _innings_total(events, 1) + 1
            distribution = self.successful_chase_distribution(venue, match_type, exclude_match_id=match_id)
            second = summarize_innings(events, 2, match_type)
            report["second_innings"] = self._second_innings_report(second, first_report, distribution, target)
        return report

    @staticmethod
    def _first_innings_report(actual: dict[str, PhaseSummary], benchmark: dict[str, Any]) -> dict[str, Any]:
        phases = {}
        for phase, summary in actual.items():
            expected = benchmark["phases"][phase]["avg_runs"]
            deviation = round(((summary.runs - expected) / expected) * 100, 1) if expected else None
            phases[phase] = {"actual_runs": summary.runs, "actual_wickets": summary.wickets,
                             "expected_runs": expected, "deviation_pct": deviation}
        return {"benchmark_sample_size": benchmark["sample_size"], "phases": phases}

    @staticmethod
    def _second_innings_report(actual: dict[str, PhaseSummary], first_report: dict[str, Any], distribution: dict[str, Any], target: int) -> dict[str, Any]:
        phases, allocated = {}, 0
        phase_names = list(actual)
        for index, phase in enumerate(phase_names):
            if index == len(phase_names) - 1:
                historical_target = target - allocated
            else:
                historical_target = round(target * distribution["phase_shares"][phase])
                allocated += historical_target
            first_deviation = first_report["phases"][phase]["deviation_pct"] or 0
            adjusted = max(0, round(historical_target * (1 + first_deviation / 100)))
            phases[phase] = {"actual_runs": actual[phase].runs, "historical_target": historical_target,
                             "first_innings_adjusted_target": adjusted,
                             "deviation_pct": round(((actual[phase].runs - adjusted) / adjusted) * 100, 1) if adjusted else None,
                             "required_run_rate_at_end": None}
        cumulative_runs = 0
        cumulative_balls = 0
        for phase in phase_names:
            cumulative_runs += actual[phase].runs
            cumulative_balls += actual[phase].legal_balls
            remaining = max(format_total_overs(distribution["format"]) * 6 - cumulative_balls, 0)
            needed = max(target - cumulative_runs, 0)
            phases[phase]["required_run_rate_at_end"] = round(needed * 6 / remaining, 2) if remaining else None
        return {"target": target, "successful_chase_sample_size": distribution["sample_size"],
                "phase_shares": distribution["phase_shares"], "phases": phases}
