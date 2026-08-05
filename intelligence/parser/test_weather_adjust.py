"""F09: weather adjustments move WP / stay silent when dry."""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from weather_service import (  # noqa: E402
    DEW_HIGH_WP_DELTA,
    compute_weather_adjustment,
)
from win_probability import apply_weather_adjustment, build_win_probability_payload  # noqa: E402


def _dists():
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
                "death": dict(phase),
            }
        },
        "venues": {},
    }


def _state():
    return {
        "format": "T20",
        "target": 160,
        "runs": 100,
        "wickets": 3,
        "legal_balls": 72,
        "legal_balls_remaining": 48,
        "runs_required": 60,
        "chase_complete": False,
    }


class WeatherAdjustTests(unittest.TestCase):
    def test_high_dew_raises_batting_wp(self):
        adj = compute_weather_adjustment({"risk": "HIGH"}, {"is_rain_code_now": False})
        self.assertIsNotNone(adj)
        base = build_win_probability_payload(_state(), _dists(), seed=7)
        adjusted = apply_weather_adjustment(dict(base), adj)
        self.assertAlmostEqual(
            adjusted["batting_wp"],
            min(1.0, base["batting_wp"] + DEW_HIGH_WP_DELTA),
            places=4,
        )
        self.assertTrue(adjusted["weather_adjusted"])
        self.assertEqual(adjusted["base_batting_wp"], base["batting_wp"])

    def test_dry_evening_no_adjustment(self):
        self.assertIsNone(compute_weather_adjustment(None, {"humidity_pct": 40}))

    def test_rain_marks_uncertain_without_wp_delta(self):
        adj = compute_weather_adjustment(None, {"is_rain_code_now": True})
        self.assertTrue(adj["uncertain"])
        self.assertEqual(adj["batting_wp_delta"], 0.0)
        base = build_win_probability_payload(_state(), _dists(), seed=3)
        adjusted = apply_weather_adjustment(dict(base), adj)
        self.assertEqual(adjusted["batting_wp"], base["batting_wp"])
        self.assertTrue(adjusted["uncertain"])

    def test_build_payload_accepts_adjustment(self):
        adj = compute_weather_adjustment({"risk": "MODERATE"}, None)
        hit = build_win_probability_payload(
            _state(), _dists(), seed=1, weather_adjustment=adj
        )
        self.assertTrue(hit["weather_adjusted"])
        self.assertIn("weather-adjusted", hit["headline"])


if __name__ == "__main__":
    unittest.main()
