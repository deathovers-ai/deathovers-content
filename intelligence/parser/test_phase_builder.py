"""Fast, self-contained checks for Phase Builder math and safety guards."""
import json
import os
import tempfile
import unittest

from phase_builder import PhaseBuilder, PhaseDataError, summarize_innings


def ball(innings, over, runs, wicket=False):
    return {"innings_num": innings, "over": over, "runs_total": runs,
            "is_legal_delivery": True, "wickets": [{}] if wicket else [],
            "batting_team": "Setters" if innings == 1 else "Chasers"}


def fixture(match_id, winner="Chasers", method=None):
    events = [ball(1, 0, 1) for _ in range(120)] + [ball(2, 0, 2) for _ in range(61)]
    outcome = {"winner": winner}
    if method: outcome["method"] = method
    return {"meta": {"venue": "Test Ground", "competition_code": "T20", "outcome": outcome}, "events": events}


class PhaseBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.events = os.path.join(self.temp.name, "events")
        os.mkdir(self.events)
        manifest = []
        for i in range(9):
            mid = str(i)
            with open(os.path.join(self.events, mid + ".json"), "w", encoding="utf8") as f: json.dump(fixture(mid), f)
            manifest.append({"match_id": mid, "competition_code": "T20"})
        self.manifest = os.path.join(self.temp.name, "manifest.json")
        with open(self.manifest, "w", encoding="utf8") as f: json.dump(manifest, f)
        self.builder = PhaseBuilder(self.events, self.manifest, min_sample_size=8)

    def tearDown(self): self.temp.cleanup()

    def test_phase_summary_counts_runs_and_wickets(self):
        summary = summarize_innings([ball(1, 0, 4), ball(1, 6, 1, True), ball(1, 15, 6)], 1, "T20")
        self.assertEqual((summary["powerplay"].runs, summary["middle"].wickets, summary["death"].runs), (4, 1, 6))

    def test_targets_sum_to_target_and_dls_is_refused(self):
        report = self.builder.analyze_match("0")
        targets = report["second_innings"]["phases"]
        self.assertEqual(sum(v["historical_target"] for v in targets.values()), report["second_innings"]["target"])
        data = fixture("dls", method="D/L")
        with open(os.path.join(self.events, "dls.json"), "w", encoding="utf8") as f: json.dump(data, f)
        with self.assertRaises(PhaseDataError): self.builder.analyze_match("dls")


if __name__ == "__main__":
    unittest.main()
