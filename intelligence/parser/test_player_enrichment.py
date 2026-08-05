"""F04: player enrichment windows, venue/phase guards, new insights."""
import unittest

from player_context import _finalize_bat, _window_from_innings, competition_code_for_match
from validation_engine import (
    MIN_PHASE_BALLS,
    MIN_VENUE_INNINGS,
    player_phase_is_reliable,
    player_venue_is_reliable,
)
from insight_engine import InsightEngine


def _empty_bowl():
    return {"runs": 0, "balls": 0, "wickets": 0, "innings": 0, "economy": 0.0, "average": None}


def _player(phase_balls=120, venue_innings=8, career_sr=130.0):
    return {
        "batting": {
            "runs": 1300, "balls": 1000, "fours": 100, "sixes": 40,
            "dismissals": 40, "innings": 50, "strike_rate": career_sr, "average": 32.5,
        },
        "bowling": _empty_bowl(),
        "earliest_match_date": "2015-01-01",
        "latest_match_date": "2026-01-01",
        "form": {
            "last_10_innings": _finalize_bat({
                "runs": 200, "balls": 120, "fours": 20, "sixes": 8,
                "dismissals": 8, "innings": 10,
            }),
        },
        "venues": {
            "Wankhede Stadium": {
                "batting": _finalize_bat({
                    "runs": 400, "balls": 280, "fours": 40, "sixes": 15,
                    "dismissals": 8, "innings": venue_innings,
                }),
                "bowling": _empty_bowl(),
            }
        },
        "phases": {
            "T20": {
                "powerplay": {
                    "runs": 100, "balls": phase_balls, "strike_rate": 120.0,
                    "reliable": phase_balls >= MIN_PHASE_BALLS,
                },
                "middle": {
                    "runs": 150, "balls": phase_balls, "strike_rate": 125.0,
                    "reliable": phase_balls >= MIN_PHASE_BALLS,
                },
                "death": {
                    "runs": 180, "balls": phase_balls, "strike_rate": 160.0,
                    "reliable": phase_balls >= MIN_PHASE_BALLS,
                },
            }
        },
    }


class PlayerEnrichmentUnitTests(unittest.TestCase):
    def test_competition_code_ipl_from_event_name(self):
        self.assertEqual(
            competition_code_for_match({"event_name": "Indian Premier League", "match_type": "T20"}),
            "IPL",
        )
        self.assertEqual(competition_code_for_match({"match_type": "T20"}), "T20")

    def test_window_from_innings_limits(self):
        rows = [
            {"runs": 10, "balls": 10, "fours": 1, "sixes": 0, "dismissals": 1},
            {"runs": 20, "balls": 10, "fours": 2, "sixes": 1, "dismissals": 1},
            {"runs": 30, "balls": 10, "fours": 3, "sixes": 1, "dismissals": 0},
        ]
        last2 = _window_from_innings(rows, 2)
        self.assertEqual(last2["innings"], 2)
        self.assertEqual(last2["runs"], 50)
        self.assertEqual(last2["balls"], 20)

    def test_venue_and_phase_guards(self):
        self.assertEqual(MIN_VENUE_INNINGS, 5)
        self.assertEqual(MIN_PHASE_BALLS, 100)
        self.assertFalse(player_venue_is_reliable({"batting": {"innings": 4}}))
        self.assertTrue(player_venue_is_reliable({"batting": {"innings": 5}}))
        self.assertFalse(player_phase_is_reliable({"balls": 50, "reliable": False}))
        self.assertTrue(player_phase_is_reliable({"balls": 120, "reliable": True}))

    def test_phase_mismatch_requires_sample_and_significance(self):
        eng = InsightEngine(player_stats={"A Player": _player()}, venue_stats={})
        thin = InsightEngine(player_stats={"A Player": _player(phase_balls=40)}, venue_stats={})
        self.assertIsNone(thin.player_phase_mismatch("A Player", "T20", "death", 40, 15))
        hit = eng.player_phase_mismatch("A Player", "T20", "death", 45, 15)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["type"], "player_phase_mismatch")
        self.assertIsNone(eng.player_phase_mismatch("A Player", "T20", "death", 25, 15))

    def test_venue_form_guard_and_insight(self):
        eng = InsightEngine(
            player_stats={"A Player": _player(venue_innings=8)},
            venue_stats={"Wankhede Stadium": {"display_name": "Wankhede Stadium"}},
        )
        hit = eng.venue_form_convergence("A Player", "Wankhede Stadium", 50, 20)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["type"], "venue_form_convergence")
        thin = InsightEngine(player_stats={"A Player": _player(venue_innings=2)}, venue_stats={})
        self.assertIsNone(thin.venue_form_convergence("A Player", "Wankhede Stadium", 50, 20))


if __name__ == "__main__":
    unittest.main()
