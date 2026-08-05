"""Toss status parsing — keeps Venue Record from showing a blank placeholder."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import (  # noqa: E402
    _format_toss_line,
    _parse_toss_from_status,
    _record_toss_if_new,
    _resolve_toss_for_match,
    _toss_archive,
)


class TossParseTests(unittest.TestCase):
    def tearDown(self):
        _toss_archive.clear()

    def test_opt_to_bowl(self):
        hit = _parse_toss_from_status("Nepal opt to bowl", "Nepal", "USA")
        self.assertEqual(hit, {"winner": "Nepal", "decision": "bowl"})

    def test_elected_to_bat(self):
        hit = _parse_toss_from_status(
            "India won the toss and elected to bat", "India", "Australia"
        )
        self.assertEqual(hit, {"winner": "India", "decision": "bat"})

    def test_field_maps_to_bowl(self):
        hit = _parse_toss_from_status(
            "England won the toss and chose to field", "England", "New Zealand"
        )
        self.assertEqual(hit, {"winner": "England", "decision": "bowl"})

    def test_live_score_line_refused(self):
        self.assertIsNone(
            _parse_toss_from_status("Sri Lanka Women need 117 runs", "SL", "IND")
        )

    def test_format_line(self):
        self.assertEqual(
            _format_toss_line({"winner": "Nepal", "decision": "bowl"}),
            "Nepal won the toss, elected to bowl",
        )

    def test_resolve_from_scorecard_status(self):
        toss = _resolve_toss_for_match(
            "m1",
            carousel_entry={"teams": ["Nepal", "USA"]},
            scorecard_data={"status": "Nepal opt to bowl"},
        )
        self.assertEqual(toss["winner"], "Nepal")
        self.assertEqual(_toss_archive["m1"]["decision"], "bowl")


if __name__ == "__main__":
    unittest.main()
