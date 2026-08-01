"""Runtime loading and explicit policy configuration for Chase Engine."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from chase_engine import ChaseEngine


@dataclass(frozen=True)
class ChasePolicy:
    t20_target_tolerance: int
    odi_target_tolerance: int
    wicket_tolerance: int
    minimum_sample: int
    recent_years: int

    @classmethod
    def from_environment(cls) -> "ChasePolicy":
        # Approved v1 defaults. Environment variables allow a reviewed change
        # without changing calculation code.
        values = {
            "t20_target_tolerance": int(os.environ.get("CHASE_T20_TARGET_TOLERANCE", "10")),
            "odi_target_tolerance": int(os.environ.get("CHASE_ODI_TARGET_TOLERANCE", "20")),
            "wicket_tolerance": int(os.environ.get("CHASE_WICKET_TOLERANCE", "1")),
            "minimum_sample": int(os.environ.get("CHASE_MINIMUM_SAMPLE", "15")),
            "recent_years": int(os.environ.get("CHASE_RECENT_YEARS", "3")),
        }
        if (values["t20_target_tolerance"] < 0 or values["odi_target_tolerance"] < 0
                or values["wicket_tolerance"] < 0 or values["minimum_sample"] < 1
                or values["recent_years"] < 1):
            raise RuntimeError("invalid chase policy")
        return cls(**values)

    def target_tolerance_for(self, match_format: str) -> int:
        return self.odi_target_tolerance if match_format in {"ODI", "ODM"} else self.t20_target_tolerance

    def cutoff_date(self, today: date | None = None) -> str:
        return ((today or date.today()) - timedelta(days=365 * self.recent_years)).isoformat()


def load_engine_from_jsonl(path: str | os.PathLike[str], cutoff_date: str | None = None) -> ChaseEngine:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"invalid chase snapshot JSONL at line {line_number}") from error
            if cutoff_date and (row.get("match_date") or "") < cutoff_date:
                continue
            rows.append(row)
    return ChaseEngine(rows)
