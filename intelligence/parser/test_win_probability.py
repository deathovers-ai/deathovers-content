"""F05: Monte Carlo win probability unit checks."""
from __future__ import annotations

import random
import unittest

from win_probability import (
    build_phase_distributions,
    build_win_probability_payload,
    resolve_phase_dist,
    simulate_chase,
)


def _tiny_dists() -> dict:
    """Minimal synthetic dists so tests do not need venue_stats.json."""
    phase = {
        "runs_per_over_mean": 8.0,
        "runs_per_over_std": 2.5,
        "wickets_per_over_mean": 0.3,
        "n": 50,
    }
    return {
        "schema_version": "phase-dist-v1",
        "formats": {
            "T20": {"powerplay": dict(phase), "middle": dict(phase), "death": {**phase, "runs_per_over_mean": 10.0}},
            "IPL": {"powerplay": dict(phase), "middle": dict(phase), "death": dict(phase)},
        },
        "venues": {},
    }


def _state(**kwargs) -> dict:
    base = {
        "format": "T20",
        "target": 160,
        "runs": 100,
        "wickets": 3,
        "legal_balls": 72,
        "legal_balls_remaining": 48,
        "runs_required": 60,
        "chase_complete": False,
    }
    base.update(kwargs)
    return base


class WinProbabilityTests(unittest.TestCase):
    def test_easy_chase_beats_hard(self):
        dists = _tiny_dists()
        easy = simulate_chase(
            _state(runs=145, wickets=2, legal_balls=96, legal_balls_remaining=24, runs_required=15),
            dists,
            n_sims=600,
            rng=random.Random(7),
        )
        hard = simulate_chase(
            _state(runs=60, wickets=8, legal_balls=96, legal_balls_remaining=24, runs_required=100),
            dists,
            n_sims=600,
            rng=random.Random(7),
        )
        self.assertIsNotNone(easy)
        self.assertIsNotNone(hard)
        self.assertGreater(easy["batting_wp"], 0.7)
        self.assertLess(hard["batting_wp"], 0.25)
        self.assertGreater(easy["batting_wp"], hard["batting_wp"])

    def test_complete_chase_is_deterministic(self):
        dists = _tiny_dists()
        won = simulate_chase(
            _state(runs=160, runs_required=0, legal_balls_remaining=12, chase_complete=True),
            dists,
            n_sims=10,
            rng=random.Random(1),
        )
        lost = simulate_chase(
            _state(runs=150, wickets=10, runs_required=10, legal_balls_remaining=0, chase_complete=True),
            dists,
            n_sims=10,
            rng=random.Random(1),
        )
        self.assertEqual(won["batting_wp"], 1.0)
        self.assertEqual(lost["batting_wp"], 0.0)

    def test_early_innings_flag(self):
        dists = _tiny_dists()
        early = simulate_chase(
            _state(legal_balls=12, legal_balls_remaining=108, runs=20, runs_required=140),
            dists,
            n_sims=200,
            rng=random.Random(3),
        )
        late = simulate_chase(
            _state(legal_balls=90, legal_balls_remaining=30, runs=120, runs_required=40),
            dists,
            n_sims=200,
            rng=random.Random(3),
        )
        self.assertTrue(early["uncertain"])
        self.assertFalse(late["uncertain"])

    def test_missing_format_silent(self):
        dists = _tiny_dists()
        hit = build_win_probability_payload(
            _state(format="TEST"),
            dists,
            n_sims=50,
            seed=1,
        )
        self.assertIsNone(hit)

    def test_ipl_falls_back_via_alias_when_only_t20(self):
        dists = _tiny_dists()
        del dists["formats"]["IPL"]
        hit = simulate_chase(_state(format="IPL"), dists, n_sims=100, rng=random.Random(2))
        self.assertIsNotNone(hit)
        self.assertEqual(hit["type"], "win_probability")

    def test_build_from_venue_stats_shape(self):
        # Minimal venue_stats stub.
        venue_stats = {
            "Demo Ground": {
                "formats": {
                    "T20": {
                        "phase_breakdown": {
                            "powerplay": {"avg_run_rate": 6.5},
                            "middle": {"avg_run_rate": 7.0},
                            "death": {"avg_run_rate": 9.0},
                        },
                        "chase_phase_breakdown": {
                            "phases": {
                                "powerplay": {"avg_run_rate": 7.0},
                                "middle": {"avg_run_rate": 7.5},
                                "death": {"avg_run_rate": 9.5},
                            }
                        },
                    }
                }
            },
            "Other Ground": {
                "formats": {
                    "T20": {
                        "phase_breakdown": {
                            "powerplay": {"avg_run_rate": 6.0},
                            "middle": {"avg_run_rate": 6.5},
                            "death": {"avg_run_rate": 8.0},
                        }
                    }
                }
            },
            "Third Ground": {
                "formats": {
                    "T20": {
                        "phase_breakdown": {
                            "powerplay": {"avg_run_rate": 7.0},
                            "middle": {"avg_run_rate": 7.2},
                            "death": {"avg_run_rate": 8.5},
                        }
                    }
                }
            },
        }
        dists = build_phase_distributions(venue_stats)
        self.assertEqual(dists["schema_version"], "phase-dist-v1")
        mid = resolve_phase_dist(dists, "T20", "middle")
        self.assertIsNotNone(mid)
        self.assertGreater(mid["runs_per_over_mean"], 0)
        self.assertGreater(mid["wickets_per_over_mean"], 0)


if __name__ == "__main__":
    unittest.main()
