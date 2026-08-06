"""Carousel-only innings must expose runs/wickets for Innings Engine UI."""
from __future__ import annotations

import unittest

import app as app_mod


class CarouselInningsShapeTests(unittest.TestCase):
    def test_parse_runs_wickets(self):
        self.assertEqual(app_mod._parse_runs_wickets("67/8"), (67, 8))
        self.assertEqual(app_mod._parse_runs_wickets("yet to bat"), (None, None))

    def test_carousel_shape_fills_runs_wickets(self):
        shaped = app_mod._shape_details_from_carousel(
            {
                "teams": ["Argentina Women", "Canada Women"],
                "score": {
                    "home": {"score": "67/8", "info": "20"},
                    "away": {"score": "70/8", "info": "17.3"},
                },
                "venue": "St George's College Ground",
                "matchFormat": "T20",
            },
            permanent=True,
        )
        self.assertEqual(shaped["innings"][0]["runs"], 67)
        self.assertEqual(shaped["innings"][0]["wickets"], 8)
        self.assertEqual(shaped["innings"][1]["runs"], 70)
        self.assertEqual(shaped["innings"][1]["wickets"], 8)


if __name__ == "__main__":
    unittest.main()
