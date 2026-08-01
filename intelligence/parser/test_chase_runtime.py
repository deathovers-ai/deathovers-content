import os
import tempfile
import unittest

from chase_runtime import ChasePolicy, load_engine_from_jsonl


class ChaseRuntimeTests(unittest.TestCase):
    def test_policy_requires_explicit_values(self):
        policy = ChasePolicy.from_environment()
        self.assertEqual(policy.target_tolerance_for("T20"), 10)
        self.assertEqual(policy.target_tolerance_for("IPL"), 10)
        self.assertEqual(policy.target_tolerance_for("ODI"), 20)
        self.assertEqual(policy.cutoff_date(today=__import__("datetime").date(2026, 8, 1)), "2023-08-02")

    def test_loads_jsonl_dataset(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
            handle.write('{"format":"T20","legal_balls":60,"target":180,"wickets":2,"runs":80,"runs_required":100,"legal_balls_remaining":60,"chase_won":true}\n')
            handle.write('{"format":"T20","match_date":"2024-01-01","legal_balls":60,"target":180,"wickets":2,"runs":80,"runs_required":100,"legal_balls_remaining":60,"chase_won":true}\n')
            path = handle.name
        try:
            engine = load_engine_from_jsonl(path)
            result = engine.evaluate(
                {"format": "T20", "legal_balls": 60, "target": 180, "wickets": 2, "runs": 80},
                target_tolerance=0, wicket_tolerance=0, minimum_sample=1, venue_scopes=[None],
            )
            self.assertEqual(result["status"], "qualified")
            filtered = load_engine_from_jsonl(path, cutoff_date="2023-08-01")
            self.assertEqual(filtered.evaluate(
                {"format": "T20", "legal_balls": 60, "target": 180, "wickets": 2, "runs": 80},
                target_tolerance=0, wicket_tolerance=0, minimum_sample=1, venue_scopes=[None],
            )["status"], "qualified")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
