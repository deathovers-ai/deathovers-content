import unittest

from chase_state import build_chase_state, cricket_overs_to_legal_balls


class ChaseStateTests(unittest.TestCase):
    def test_t20_chase_state(self):
        state = build_chase_state(match_id="m1", match_format="T20", runs=142, wickets=4, legal_balls=102, target=181)
        self.assertEqual(state["runs_required"], 39)
        self.assertEqual(state["legal_balls_remaining"], 18)
        self.assertEqual(state["required_run_rate"], 13.0)
        self.assertFalse(state["chase_complete"])

    def test_cricket_overs_are_not_decimals(self):
        self.assertEqual(cricket_overs_to_legal_balls("17.3"), 105)
        with self.assertRaises(ValueError):
            cricket_overs_to_legal_balls("17.6")

    def test_invalid_state_is_rejected(self):
        with self.assertRaises(ValueError):
            build_chase_state(match_id="m1", match_format="Test", runs=1, wickets=0, legal_balls=1, target=2)


if __name__ == "__main__":
    unittest.main()
