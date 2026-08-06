"""F12: What-If simulator unit checks."""
from __future__ import annotations

import unittest

from what_if import (
    WhatIfError,
    apply_fork,
    run_what_if,
    run_what_if_request,
    state_from_scoreboard,
    validate_xi,
)


def _tiny_dists() -> dict:
    phase = {
        "runs_per_over_mean": 8.0,
        "runs_per_over_std": 2.5,
        "wickets_per_over_mean": 0.3,
        "n": 50,
    }
    return {
        "schema_version": "phase-dist-v1",
        "formats": {
            "T20": {
                "powerplay": dict(phase),
                "middle": dict(phase),
                "death": {**phase, "runs_per_over_mean": 10.0},
            },
        },
        "venues": {},
    }


class WhatIfTests(unittest.TestCase):
    def test_xi_rejects_twelfth_and_non_xi_order(self):
        with self.assertRaises(WhatIfError):
            validate_xi([f"P{i}" for i in range(12)], None)
        with self.assertRaises(WhatIfError):
            validate_xi(["A", "B"], ["C"])
        ok = validate_xi(["V Kohli", "RG Sharma"], ["RG Sharma", "V Kohli"])
        self.assertEqual(ok["batting_order"][0], "RG Sharma")

    def test_fewer_wickets_raises_batting_wp(self):
        baseline = state_from_scoreboard(
            match_format="T20",
            target=160,
            runs=100,
            wickets=5,
            overs="12.0",
        )
        out = run_what_if(
            baseline=baseline,
            fork={"wickets": 2},
            dists=_tiny_dists(),
            xi=["A", "B", "C"],
            batting_order=["B", "A"],
            n_sims=800,
            seed=7,
        )
        self.assertEqual(out["schema_version"], "what-if-v1")
        self.assertIn("disclaimer", out)
        self.assertGreater(out["comparison"]["batting_wp_delta"], 0)
        self.assertEqual(out["simulated"]["state"]["wickets"], 2)
        self.assertEqual(out["baseline"]["state"]["wickets"], 5)

    def test_request_parser_scoreboard(self):
        out = run_what_if_request(
            {
                "baseline": {
                    "format": "T20",
                    "target": 180,
                    "runs": 90,
                    "wickets": 3,
                    "overs": "10.0",
                },
                "fork": {"wickets": 6},
                "n_sims": 400,
                "seed": 1,
            },
            dists=_tiny_dists(),
        )
        self.assertLess(out["comparison"]["batting_wp_delta"], 0)

    def test_apply_fork_unknown_key(self):
        baseline = state_from_scoreboard(
            match_format="T20", target=150, runs=50, wickets=1, overs="6.0"
        )
        with self.assertRaises(WhatIfError):
            apply_fork(baseline, {"magic": 1})


if __name__ == "__main__":
    unittest.main()
