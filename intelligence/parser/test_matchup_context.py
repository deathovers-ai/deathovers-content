"""F06: matchup matrix guards + bowler_batter_matchup insight."""
import unittest

from validation_engine import MIN_MATCHUP_BALLS, matchup_is_reliable
from insight_engine import InsightEngine


def _pair(balls=40, runs=60, dismissals=2):
    return {
        "balls": balls,
        "runs": runs,
        "dismissals": dismissals,
        "strike_rate": round((runs / balls) * 100, 2) if balls else 0.0,
        "average": round(runs / dismissals, 2) if dismissals else None,
        "reliable": balls >= MIN_MATCHUP_BALLS,
    }


class MatchupUnitTests(unittest.TestCase):
    def test_matchup_floor(self):
        self.assertEqual(MIN_MATCHUP_BALLS, 30)
        self.assertFalse(matchup_is_reliable(_pair(balls=29)))
        self.assertTrue(matchup_is_reliable(_pair(balls=30)))
        self.assertFalse(matchup_is_reliable(None))

    def test_matchup_insight_fires_and_refuses_thin(self):
        eng = InsightEngine(
            player_stats={
                "A Batter": {
                    "batting": {"strike_rate": 120.0, "runs": 1200, "balls": 1000},
                    "earliest_match_date": "2015-01-01",
                    "latest_match_date": "2026-01-01",
                }
            },
            venue_stats={},
            matchup_stats={"A Batter": {"A Bowler": _pair(balls=40, runs=80, dismissals=1)}},
        )
        hit = eng.bowler_batter_matchup("A Batter", "A Bowler")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["type"], "bowler_batter_matchup")
        self.assertEqual(hit["balls"], 40)

        thin = InsightEngine(
            player_stats={},
            venue_stats={},
            matchup_stats={"A Batter": {"A Bowler": _pair(balls=20)}},
        )
        self.assertIsNone(thin.bowler_batter_matchup("A Batter", "A Bowler"))

    def test_generate_all_includes_matchup_when_both_live(self):
        eng = InsightEngine(
            player_stats={
                "A Batter": {
                    "batting": {"strike_rate": 100.0, "runs": 500, "balls": 500},
                    "earliest_match_date": "2018-01-01",
                    "latest_match_date": "2026-01-01",
                }
            },
            venue_stats={},
            matchup_stats={"A Batter": {"A Bowler": _pair(balls=50, runs=50)}},
        )
        insights = eng.generate_all({
            "player_name": "A Batter",
            "player_current_runs": 20,
            "player_current_balls": 15,
            "bowler_name": "A Bowler",
        })
        types = {i["type"] for i in insights}
        self.assertIn("bowler_batter_matchup", types)


if __name__ == "__main__":
    unittest.main()
