"""F01 + F11: phase boundaries — over-based T20/ODI; ball-native Hundred."""
import unittest

from constants import (
    PHASE_BOUNDARIES,
    PHASE_BOUNDARIES_BALLS,
    balls_per_over_for_match_type,
    determine_phase_from_balls,
    determine_phase_from_over,
    format_total_overs,
    innings_legal_balls,
    is_ball_native_format,
    is_experimental_format,
    overs_to_legal_balls,
    phase_bounds_balls,
    phase_bounds_list,
    phase_kind_for_match_type,
    phase_set_for_match_type,
    phase_set_for_total_overs,
)
from match_intelligence_api import determine_phase, map_format
from context_repository import phase_set_for_format


class PhaseConstantsTests(unittest.TestCase):
    def test_canonical_t20_odi_windows_unchanged(self):
        self.assertEqual(PHASE_BOUNDARIES["T20_LIKE"]["powerplay"], (0, 6))
        self.assertEqual(PHASE_BOUNDARIES["T20_LIKE"]["death"], (15, 20))
        self.assertEqual(PHASE_BOUNDARIES["ODI_LIKE"]["powerplay"], (0, 10))
        self.assertEqual(PHASE_BOUNDARIES["ODI_LIKE"]["death"], (40, 50))
        # Isolation: Hundred must not live in the over table; T10 deferred.
        self.assertNotIn("HUNDRED", PHASE_BOUNDARIES)
        self.assertNotIn("T10_LIKE", PHASE_BOUNDARIES)

    def test_hundred_ball_native_official_pp(self):
        self.assertEqual(PHASE_BOUNDARIES_BALLS["HUNDRED"]["powerplay"], (0, 25))
        self.assertEqual(PHASE_BOUNDARIES_BALLS["HUNDRED"]["middle"], (25, 75))
        self.assertEqual(PHASE_BOUNDARIES_BALLS["HUNDRED"]["death"], (75, 100))
        self.assertTrue(is_ball_native_format("HUNDRED"))
        self.assertFalse(is_ball_native_format("T20"))
        self.assertFalse(is_ball_native_format("ODI"))
        self.assertEqual(balls_per_over_for_match_type("HUNDRED"), 5)
        self.assertEqual(innings_legal_balls("HND"), 100)

    def test_hundred_cricsheet_over_adapter_derived_from_balls(self):
        self.assertEqual(phase_set_for_match_type("HUNDRED")["powerplay"], (0, 5))
        self.assertEqual(phase_set_for_match_type("HND")["death"], (15, 20))

    def test_t10_deferred(self):
        # T10 maps to T20_LIKE fallback until we add it deliberately.
        self.assertEqual(phase_kind_for_match_type("T10"), "T20_LIKE")
        self.assertIsNone(map_format("T10"))
        self.assertFalse(is_experimental_format("ODI"))
        self.assertEqual(format_total_overs("T10"), 20)  # T20_LIKE path

    def test_ipl_matches_t20_windows(self):
        self.assertEqual(phase_bounds_list("IPL"), phase_bounds_list("T20"))
        self.assertEqual(phase_bounds_list("IT20"), phase_bounds_list("T20"))

    def test_determine_phase_boundaries(self):
        self.assertEqual(determine_phase(5, "T20"), "powerplay")
        self.assertEqual(determine_phase(6, "T20"), "middle")
        self.assertEqual(determine_phase(14, "T20"), "middle")
        self.assertEqual(determine_phase(15, "T20"), "death")
        self.assertEqual(determine_phase(39, "ODI"), "middle")
        self.assertEqual(determine_phase(40, "ODI"), "death")
        self.assertEqual(determine_phase(4, "HUNDRED"), "powerplay")
        self.assertEqual(determine_phase(5, "HUNDRED"), "middle")
        self.assertEqual(determine_phase(15, "HND"), "death")

    def test_hundred_phase_from_balls(self):
        self.assertEqual(determine_phase_from_balls(0, "HUNDRED"), "powerplay")
        self.assertEqual(determine_phase_from_balls(24, "HUNDRED"), "powerplay")
        self.assertEqual(determine_phase_from_balls(25, "HUNDRED"), "middle")
        self.assertEqual(determine_phase_from_balls(74, "HND"), "middle")
        self.assertEqual(determine_phase_from_balls(75, "HND"), "death")
        self.assertEqual(determine_phase_from_balls(99, "100"), "death")

    def test_overs_to_balls_isolation(self):
        self.assertEqual(overs_to_legal_balls(6.3, "T20"), 39)
        self.assertEqual(overs_to_legal_balls(6.3, "ODI"), 39)
        self.assertEqual(overs_to_legal_balls(5.0, "HUNDRED"), 25)
        self.assertEqual(overs_to_legal_balls(4.4, "HUNDRED"), 24)

    def test_api_matches_constants_helper(self):
        for over, fmt in (
            (0, "T20"),
            (5.5, "IPL"),
            (10, "ODI"),
            (45, "ODM"),
            (4, "HUNDRED"),
        ):
            self.assertEqual(determine_phase(over, fmt), determine_phase_from_over(over, fmt))

    def test_context_repo_never_infers_hundred_from_20_overs(self):
        self.assertEqual(phase_set_for_format(20), phase_set_for_total_overs(20))
        self.assertIs(phase_set_for_format(20), PHASE_BOUNDARIES["T20_LIKE"])
        self.assertEqual(phase_set_for_format(50), phase_set_for_match_type("ODI"))
        # Short innings without match_type → T20_LIKE (T10 not supported).
        self.assertIs(phase_set_for_format(10), PHASE_BOUNDARIES["T20_LIKE"])
        self.assertEqual(
            phase_set_for_format(20, match_type="HUNDRED")["powerplay"],
            (0, 5),
        )

    def test_odi_vs_t20_not_confused(self):
        self.assertEqual(determine_phase(8, "ODI"), "powerplay")
        self.assertEqual(determine_phase(8, "T20"), "middle")

    def test_hundred_vs_t20_not_confused(self):
        self.assertEqual(determine_phase_from_balls(25, "HUNDRED"), "middle")
        self.assertEqual(determine_phase(5, "T20"), "powerplay")
        self.assertEqual(phase_bounds_balls("T20")[0], ("powerplay", 0, 36))
        self.assertEqual(phase_bounds_balls("HUNDRED")[0], ("powerplay", 0, 25))

    def test_live_format_map(self):
        self.assertEqual(map_format("ODI"), "ODI")
        self.assertEqual(map_format("Hundred"), "HUNDRED")
        self.assertEqual(map_format("100"), "HUNDRED")
        self.assertEqual(map_format("T20I"), "T20")
        self.assertEqual(phase_kind_for_match_type("IPL"), "T20_LIKE")


if __name__ == "__main__":
    unittest.main()
