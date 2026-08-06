"""F01 + F11: phase boundaries from one table, including Hundred / T10 / ODI."""
import unittest

from constants import (
    PHASE_BOUNDARIES,
    balls_per_over_for_match_type,
    format_total_overs,
    innings_legal_balls,
    is_experimental_format,
    phase_bounds_list,
    phase_kind_for_match_type,
    phase_set_for_match_type,
    phase_set_for_total_overs,
    determine_phase_from_over,
)
from match_intelligence_api import determine_phase, map_format
from context_repository import phase_set_for_format


class PhaseConstantsTests(unittest.TestCase):
    def test_canonical_t20_odi_windows(self):
        self.assertEqual(PHASE_BOUNDARIES["T20_LIKE"]["powerplay"], (0, 6))
        self.assertEqual(PHASE_BOUNDARIES["T20_LIKE"]["death"], (15, 20))
        self.assertEqual(PHASE_BOUNDARIES["ODI_LIKE"]["powerplay"], (0, 10))
        self.assertEqual(PHASE_BOUNDARIES["ODI_LIKE"]["death"], (40, 50))

    def test_hundred_windows_25_ball_powerplay(self):
        # 5-ball overs: first 5 overs = 25 balls (official Hundred PP).
        self.assertEqual(PHASE_BOUNDARIES["HUNDRED"]["powerplay"], (0, 5))
        self.assertEqual(PHASE_BOUNDARIES["HUNDRED"]["middle"], (5, 15))
        self.assertEqual(PHASE_BOUNDARIES["HUNDRED"]["death"], (15, 20))
        self.assertEqual(balls_per_over_for_match_type("HUNDRED"), 5)
        self.assertEqual(innings_legal_balls("HND"), 100)
        self.assertEqual(phase_kind_for_match_type("100"), "HUNDRED")
        self.assertEqual(phase_kind_for_match_type("HND"), "HUNDRED")

    def test_t10_windows_experimental(self):
        self.assertEqual(PHASE_BOUNDARIES["T10_LIKE"]["powerplay"], (0, 3))
        self.assertEqual(PHASE_BOUNDARIES["T10_LIKE"]["death"], (7, 10))
        self.assertTrue(is_experimental_format("T10"))
        self.assertFalse(is_experimental_format("ODI"))
        self.assertEqual(innings_legal_balls("T10"), 60)
        self.assertEqual(format_total_overs("T10"), 10)

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
        self.assertEqual(determine_phase(2, "T10"), "powerplay")
        self.assertEqual(determine_phase(3, "T10"), "middle")
        self.assertEqual(determine_phase(7, "T10"), "death")

    def test_api_matches_constants_helper(self):
        for over, fmt in (
            (0, "T20"),
            (5.5, "IPL"),
            (10, "ODI"),
            (45, "ODM"),
            (4, "HUNDRED"),
            (8, "T10"),
        ):
            self.assertEqual(determine_phase(over, fmt), determine_phase_from_over(over, fmt))

    def test_context_repo_uses_shared_table(self):
        self.assertEqual(phase_set_for_format(20), phase_set_for_total_overs(20))
        self.assertEqual(phase_set_for_format(50), phase_set_for_match_type("ODI"))
        self.assertEqual(phase_set_for_format(10), phase_set_for_match_type("T10"))
        self.assertIs(phase_set_for_format(20), PHASE_BOUNDARIES["T20_LIKE"])
        # Match type wins over total overs when both given (Hundred ≠ T20).
        self.assertIs(
            phase_set_for_format(20, match_type="HUNDRED"),
            PHASE_BOUNDARIES["HUNDRED"],
        )

    def test_live_format_map(self):
        self.assertEqual(map_format("ODI"), "ODI")
        self.assertEqual(map_format("T10"), "T10")
        self.assertEqual(map_format("Hundred"), "HUNDRED")
        self.assertEqual(map_format("100"), "HUNDRED")
        self.assertEqual(map_format("T20I"), "T20")


if __name__ == "__main__":
    unittest.main()
