"""Query the compressed, pre-aggregated Chase Index."""
import gzip
import json
from pathlib import Path


class CompactChaseEngine:
    def __init__(self, buckets): self.buckets = buckets

    @classmethod
    def load(cls, path):
        with gzip.open(Path(path), "rt", encoding="utf-8") as source:
            payload = json.load(source)
        if payload.get("schema_version") != "compact-chase-index-v1":
            raise RuntimeError("unsupported compact chase index")
        return cls(payload["buckets"])

    def evaluate(self, state, *, target_tolerance, wicket_tolerance, minimum_sample, venue_scopes):
        for venue in venue_scopes:
            total = wins = 0; run_sum = wicket_sum = rrr_sum = 0.0
            for target in range(state["target"] - target_tolerance, state["target"] + target_tolerance + 1):
                for wickets in range(max(0, state["wickets"] - wicket_tolerance), min(10, state["wickets"] + wicket_tolerance) + 1):
                    values = self.buckets.get(f'{state["format"]}|{venue}|{state["legal_balls"]}|{target}|{wickets}')
                    if not values: continue
                    total += values[0]; wins += values[1]; run_sum += values[2]; wicket_sum += values[3]; rrr_sum += values[4]
            if total >= minimum_sample:
                avg_runs = run_sum / wins if wins else None
                avg_wickets = wicket_sum / wins if wins else None
                return {"status":"qualified","cohort":{"venue_scope":venue,"sample_size":total,"wins":wins,"recovery_rate":wins/total,"average_successful_runs":avg_runs,"average_successful_wickets":avg_wickets,"average_successful_rrr":rrr_sum/wins if wins else None,"pace_gap_runs":state["runs"]-avg_runs if avg_runs is not None else None,"wicket_gap":state["wickets"]-avg_wickets if avg_wickets is not None else None}}
        return {"status":"insufficient_evidence","reason":"no approved cohort met the minimum sample","minimum_sample":minimum_sample}
