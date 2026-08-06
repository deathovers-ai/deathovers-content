"""F02: validation guards live in validation_engine and still block Kallis."""
import json
import os
import unittest

from validation_engine import (
    DATA_CONFIDENCE_CUTOFF,
    MIN_VENUE_MATCHES,
    SIGNIFICANCE_THRESHOLD_BY_KIND,
    SIGNIFICANCE_THRESHOLD_PCT,
    player_data_is_reliable,
    significance_threshold_pct,
    venue_data_is_reliable,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYER_STATS = os.path.join(BASE_DIR, "output", "context", "player_stats.json")


class ValidationEngineTests(unittest.TestCase):
    def test_threshold_constants(self):
        self.assertEqual(DATA_CONFIDENCE_CUTOFF, "2005-01-01")
        self.assertEqual(SIGNIFICANCE_THRESHOLD_PCT, 10.0)
        self.assertEqual(MIN_VENUE_MATCHES, 5)
        self.assertEqual(SIGNIFICANCE_THRESHOLD_BY_KIND["ODI_LIKE"], 8.0)
        self.assertEqual(SIGNIFICANCE_THRESHOLD_BY_KIND["HUNDRED"], 12.0)
        self.assertEqual(significance_threshold_pct("ODI"), 8.0)
        self.assertEqual(significance_threshold_pct("T20"), 10.0)
        self.assertEqual(significance_threshold_pct("HUNDRED"), 12.0)
        self.assertEqual(significance_threshold_pct("TEST"), 10.0)

    def test_player_missing_date_refused(self):
        self.assertFalse(player_data_is_reliable({}))
        self.assertFalse(player_data_is_reliable({"earliest_match_date": None}))

    def test_player_pre_cutoff_refused(self):
        self.assertFalse(player_data_is_reliable({"earliest_match_date": "2004-12-31"}))
        self.assertTrue(player_data_is_reliable({"earliest_match_date": "2005-01-01"}))

    def test_kallis_refused_from_real_stats(self):
        if not os.path.exists(PLAYER_STATS):
            self.skipTest("player_stats.json not present")
        with open(PLAYER_STATS, encoding="utf-8") as f:
            players = json.load(f)
        kallis = players.get("JH Kallis")
        if kallis is None:
            self.skipTest("JH Kallis not in player_stats.json")
        self.assertFalse(
            player_data_is_reliable(kallis),
            f"Kallis earliest={kallis.get('earliest_match_date')} should be refused",
        )
        # Guard must remain stricter than his recorded earliest date alone implies
        # for naive cutoffs — recorded career in our corpus starts 2003, cutoff is 2005.
        self.assertLess(kallis["earliest_match_date"], DATA_CONFIDENCE_CUTOFF)

    def test_kohli_allowed_from_real_stats(self):
        if not os.path.exists(PLAYER_STATS):
            self.skipTest("player_stats.json not present")
        with open(PLAYER_STATS, encoding="utf-8") as f:
            players = json.load(f)
        kohli = players.get("V Kohli")
        if kohli is None:
            self.skipTest("V Kohli not in player_stats.json")
        self.assertTrue(player_data_is_reliable(kohli))

    def test_venue_confidence_and_sample_guards(self):
        self.assertFalse(venue_data_is_reliable({}, "T20"))
        self.assertFalse(venue_data_is_reliable(
            {"formats": {"T20": {"confidence": "low", "matches_with_data": 100}}}, "T20"
        ))
        self.assertTrue(venue_data_is_reliable(
            {"formats": {"T20": {"confidence": "medium", "matches_with_data": 3}}}, "T20"
        ))
        self.assertFalse(venue_data_is_reliable(
            {"formats": {"T20": {"matches_with_data": 4}}}, "T20"
        ))
        self.assertTrue(venue_data_is_reliable(
            {"formats": {"T20": {"matches_with_data": 5}}}, "T20"
        ))


if __name__ == "__main__":
    unittest.main()
