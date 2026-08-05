"""F07: continuous momentum index + percentile baselines."""
import unittest

from momentum_index import (
    MIN_WINDOW,
    WINDOW,
    compute_momentum_index,
    build_momentum_insight,
    momentum_label,
    lookup_percentile,
)


def _balls(pattern):
    """pattern: list of runs; use 'W' for wicket with 0 runs."""
    out = []
    for p in pattern:
        if p == "W":
            out.append({"runs_total": 0, "is_wicket": True})
        else:
            out.append({"runs_total": int(p), "is_wicket": False})
    return out


class MomentumIndexUnitTests(unittest.TestCase):
    def test_window_floor(self):
        self.assertIsNone(compute_momentum_index(_balls([1] * (MIN_WINDOW - 1)), 120.0))
        self.assertIsNotNone(compute_momentum_index(_balls([1] * MIN_WINDOW), 120.0))

    def test_surge_vs_slump(self):
        hot = _balls([6, 4, 4, 6, 1, 4, 6, 4, 1, 6, 4, 4, 6, 1, 4, 6, 4, 1])
        cold = _balls([0, 0, "W", 0, 0, 0, 1, 0, 0, "W", 0, 0, 0, 0, 1, 0, 0, 0])
        hot_i = compute_momentum_index(hot, 120.0)
        cold_i = compute_momentum_index(cold, 120.0)
        self.assertGreater(hot_i, 0.4)
        self.assertLess(cold_i, -0.2)
        self.assertEqual(momentum_label(hot_i), "SURGING")
        self.assertIn(momentum_label(cold_i), ("STALLING", "SLUMPING"))

    def test_index_bounds(self):
        crazy = _balls([6] * WINDOW)
        idx = compute_momentum_index(crazy, 100.0)
        self.assertGreaterEqual(idx, -1.0)
        self.assertLessEqual(idx, 1.0)

    def test_insight_and_percentile(self):
        baselines = {
            "formats": {
                "T20": {
                    "middle": {
                        "n": 500,
                        "p10": -0.5, "p25": -0.2, "p50": 0.0, "p75": 0.2, "p90": 0.5,
                        "samples": [i / 100 for i in range(-50, 51)],
                    }
                }
            }
        }
        balls = _balls([4, 6, 1, 4, 6, 4, 1, 6, 4, 4, 6, 1, 4, 6, 1, 4, 6, 4])
        hit = build_momentum_insight(balls, 120.0, "T20", "middle", baselines)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["type"], "momentum_index")
        self.assertGreater(hit["index"], 0)
        self.assertIsNotNone(hit["percentile"])
        self.assertGreater(hit["percentile"], 50)

    def test_lookup_requires_sample_floor(self):
        thin = {"formats": {"T20": {"death": {"n": 50, "p50": 0.0, "samples": [0.0] * 50}}}}
        self.assertIsNone(lookup_percentile(thin, "T20", "death", 0.1))


if __name__ == "__main__":
    unittest.main()
