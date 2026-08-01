import unittest

from chase_cohort import select_cohort, summarize_cohort


ROWS = [
    {"format": "T20", "venue": "A", "legal_balls": 60, "target": 181, "wickets": 2, "runs": 86, "runs_required": 95, "legal_balls_remaining": 60, "chase_won": True},
    {"format": "T20", "venue": "A", "legal_balls": 60, "target": 180, "wickets": 3, "runs": 75, "runs_required": 105, "legal_balls_remaining": 60, "chase_won": False},
    {"format": "T20", "venue": "B", "legal_balls": 60, "target": 181, "wickets": 2, "runs": 90, "runs_required": 91, "legal_balls_remaining": 60, "chase_won": True},
    {"format": "ODI", "venue": "A", "legal_balls": 60, "target": 181, "wickets": 2, "runs": 86, "runs_required": 95, "legal_balls_remaining": 240, "chase_won": True},
]
STATE = {"format": "T20", "legal_balls": 60, "target": 180, "wickets": 2, "runs": 80}


class ChaseCohortTests(unittest.TestCase):
    def test_selects_exact_match_point_with_explicit_tolerances(self):
        result = select_cohort(ROWS, STATE, target_tolerance=1, wicket_tolerance=1, venue="A")
        self.assertEqual(len(result), 2)

    def test_summary_uses_successful_chases_for_par_comparison(self):
        cohort = select_cohort(ROWS, STATE, target_tolerance=1, wicket_tolerance=1, venue="A")
        result = summarize_cohort(cohort, STATE)
        self.assertEqual(result["sample_size"], 2)
        self.assertEqual(result["wins"], 1)
        self.assertEqual(result["recovery_rate"], 0.5)
        self.assertEqual(result["median_successful_runs"], 86)
        self.assertEqual(result["pace_gap_runs"], -6)

    def test_empty_cohort_has_no_implied_metrics(self):
        self.assertEqual(summarize_cohort([], STATE), {"sample_size": 0, "wins": 0, "recovery_rate": None})


if __name__ == "__main__":
    unittest.main()
