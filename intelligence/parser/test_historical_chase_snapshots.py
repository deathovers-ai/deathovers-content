import unittest

from historical_chase_snapshots import build_chase_snapshots


def event(innings, team, opponent, runs, legal=True, wickets=None):
    return {
        "innings_num": innings,
        "batting_team": team,
        "bowling_team": opponent,
        "runs_total": runs,
        "is_legal_delivery": legal,
        "wickets": wickets or [],
    }


def match(outcome=None, match_type="T20"):
    return {
        "match_id": "m1",
        "meta": {
            "match_id": "m1",
            "match_type": match_type,
            "venue": "Test Ground",
            "season": "2026",
            "dates": ["2026-01-01"],
            "outcome": outcome or {"winner": "Chasers"},
        },
        "events": [
            event(1, "Defenders", "Chasers", 4),
            event(1, "Defenders", "Chasers", 6),
            event(2, "Chasers", "Defenders", 1),
            event(2, "Chasers", "Defenders", 4, legal=False),
            event(2, "Chasers", "Defenders", 6, wickets=[{"player_out": "A"}]),
        ],
    }


class HistoricalChaseSnapshotTests(unittest.TestCase):
    def test_snapshots_use_legal_balls_but_include_all_runs(self):
        snapshots = build_chase_snapshots(match())
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0]["target"], 11)
        self.assertEqual(snapshots[0]["legal_balls"], 1)
        self.assertEqual(snapshots[1]["legal_balls"], 2)
        self.assertEqual(snapshots[1]["runs"], 11)
        self.assertEqual(snapshots[1]["wickets"], 1)
        self.assertEqual(snapshots[1]["match_date"], "2026-01-01")
        self.assertTrue(snapshots[1]["chase_won"])
        self.assertEqual(snapshots[0]["final_runs"], 11)

    def test_no_result_tie_and_revised_target_are_excluded(self):
        self.assertEqual(build_chase_snapshots(match({"result": "no result"})), [])
        self.assertEqual(build_chase_snapshots(match({"result": "tie"})), [])
        self.assertEqual(build_chase_snapshots(match({"winner": "Chasers", "method": "DLS"})), [])

    def test_unsupported_format_is_excluded(self):
        self.assertEqual(build_chase_snapshots(match(match_type="Test")), [])

    def test_ipl_competition_is_kept_separate_from_general_t20(self):
        data = match()
        data["meta"]["competition_code"] = "IPL"
        self.assertEqual(build_chase_snapshots(data)[0]["format"], "IPL")


if __name__ == "__main__":
    unittest.main()
