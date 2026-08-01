"""Evidence-gated Chase Engine orchestration."""
from __future__ import annotations

from typing import Any, Iterable

from chase_cohort import select_cohort, summarize_cohort


class ChaseEngine:
    """Runs only caller-approved cohort policies; never chooses fallbacks itself."""

    def __init__(self, snapshots: Iterable[dict[str, Any]]) -> None:
        self._snapshots = list(snapshots)

    def evaluate(
        self,
        state: dict[str, Any],
        *,
        target_tolerance: int,
        wicket_tolerance: int,
        minimum_sample: int,
        venue_scopes: list[str | None],
    ) -> dict[str, Any]:
        if minimum_sample < 1:
            raise ValueError("minimum_sample must be positive")
        if not venue_scopes:
            raise ValueError("venue_scopes must be an explicit ordered policy")

        for venue in venue_scopes:
            cohort = select_cohort(
                self._snapshots,
                state,
                target_tolerance=target_tolerance,
                wicket_tolerance=wicket_tolerance,
                venue=venue,
            )
            facts = summarize_cohort(cohort, state)
            if facts["sample_size"] >= minimum_sample:
                return {
                    "status": "qualified",
                    "cohort": {
                        "venue_scope": venue,
                        "target_tolerance": target_tolerance,
                        "wicket_tolerance": wicket_tolerance,
                        **facts,
                    },
                }
        return {
            "status": "insufficient_evidence",
            "reason": "no approved cohort met the minimum sample",
            "minimum_sample": minimum_sample,
        }
