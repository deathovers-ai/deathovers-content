import unittest

from chase_engine import ChaseEngine


ROWS = [
    {"format": "T20", "venue": "A", "legal_balls": 60, "target": 180, "wickets": 2, "runs": 82, "runs_required": 98, "legal_balls_remaining": 60, "chase_won": True},
    {"format": "T20", "venue": "A", "legal_balls": 60, "target": 180, "wickets": 2, "runs": 78, "runs_required": 102, "legal_balls_remaining": 60, "chase_won": False},
    {"format": "T20", "venue": "B", "legal_balls": 60, "target": 180, "wickets": 2, "runs": 85, "runs_required": 95, "legal_balls_remaining": 60, "chase_won": True},
]
STATE = {"format": "T20", "legal_balls": 60, "target": 180, "wickets": 2, "runs": 80}


class ChaseEngineTests(unittest.TestCase):
    def test_uses_the_first_approved_scope_that_meets_sample(self):
        result = ChaseEngine(ROWS).evaluate(
            STATE, target_tolerance=0, wicket_tolerance=0, minimum_sample=2, venue_scopes=["A", None]
        )
        self.assertEqual(result["status"], "qualified")
        self.assertEqual(result["cohort"]["venue_scope"], "A")
        self.assertEqual(result["cohort"]["sample_size"], 2)

    def test_refuses_when_policy_has_insufficient_evidence(self):
        result = ChaseEngine(ROWS).evaluate(
            STATE, target_tolerance=0, wicket_tolerance=0, minimum_sample=4, venue_scopes=["A", None]
        )
        self.assertEqual(result["status"], "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
