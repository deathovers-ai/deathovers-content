"""F10: Tactical Decision Assistant unit checks."""
from __future__ import annotations

import unittest

from decision_assistant import build_tactical_board


def _chase(*, rrr=10.5, wickets=3, balls=48, qualified=True, pace_gap=-5.0, recovery=0.42, sample=40):
    state = {
        "format": "T20",
        "target": 170,
        "runs": 90,
        "wickets": wickets,
        "legal_balls": 120 - balls,
        "legal_balls_remaining": balls,
        "runs_required": 80,
        "required_run_rate": rrr,
        "chase_complete": False,
    }
    chase = {"status": "qualified" if qualified else "insufficient_evidence", "state": state}
    if qualified:
        chase["cohort"] = {
            "sample_size": sample,
            "recovery_rate": recovery,
            "pace_gap_runs": pace_gap,
            "venue_scope": "Wankhede Stadium",
        }
    return chase


class DecisionAssistantTests(unittest.TestCase):
    def test_promote_hitter_cites_cohort(self):
        board = build_tactical_board(chase=_chase(rrr=10.5, wickets=3, balls=48, pace_gap=-8))
        self.assertIsNotNone(board)
        self.assertEqual(board["confidence"], "medium")
        self.assertIn("disclaimer", board)
        ids = [d["id"] for d in board["decisions"]]
        self.assertIn("promote_hitter", ids)
        promote = next(d for d in board["decisions"] if d["id"] == "promote_hitter")
        self.assertEqual(promote["sample"]["sample_size"], 40)
        self.assertEqual(promote["confidence"], "medium")

    def test_silence_without_cohort_sample(self):
        board = build_tactical_board(chase=_chase(qualified=False))
        # No cohort → no chase decisions; empty insights → None
        self.assertIsNone(board)

    def test_matchup_caution_from_insight(self):
        insights = [
            {
                "type": "bowler_batter_matchup",
                "headline": "X vs Y: 85 SR historically (40 balls)",
                "pointers": [
                    {"label": "Strike Rate", "value": 85},
                    {"label": "Balls", "value": 40},
                    {"label": "Dismissals", "value": 3},
                ],
            }
        ]
        board = build_tactical_board(chase={"status": "not_a_live_second_innings"}, insights=insights)
        self.assertIsNotNone(board)
        self.assertEqual(board["decisions"][0]["id"], "matchup_caution")

    def test_consolidate_when_ahead(self):
        board = build_tactical_board(chase=_chase(rrr=6.0, wickets=2, balls=60, pace_gap=12.0, recovery=0.55))
        ids = [d["id"] for d in board["decisions"]]
        self.assertIn("consolidate", ids)
        self.assertNotIn("promote_hitter", ids)


if __name__ == "__main__":
    unittest.main()
