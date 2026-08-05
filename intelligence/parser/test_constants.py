"""F01: phase boundaries must come from one table."""
import unittest

from constants import (
    PHASE_BOUNDARIES,
    phase_bounds_list,
    phase_set_for_match_type,
    phase_set_for_total_overs,
    determine_phase_from_over,
)
from match_intelligence_api import determine_phase
from context_repository import phase_set_for_format


class PhaseConstantsTests(unittest.TestCase):
    def test_canonical_windows(self):
        self.assertEqual(PHASE_BOUNDARIES["T20_LIKE"]["powerplay"], (0, 6))
        self.assertEqual(PHASE_BOUNDARIES["T20_LIKE"]["death"], (15, 20))
        self.assertEqual(PHASE_BOUNDARIES["ODI_LIKE"]["powerplay"], (0, 10))
        self.assertEqual(PHASE_BOUNDARIES["ODI_LIKE"]["death"], (40, 50))

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

    def test_api_matches_constants_helper(self):
        for over, fmt in ((0, "T20"), (5.5, "IPL"), (10, "ODI"), (45, "ODM")):
            self.assertEqual(determine_phase(over, fmt), determine_phase_from_over(over, fmt))

    def test_context_repo_uses_shared_table(self):
        self.assertEqual(phase_set_for_format(20), phase_set_for_total_overs(20))
        self.assertEqual(phase_set_for_format(50), phase_set_for_match_type("ODI"))
        self.assertIs(phase_set_for_format(20), PHASE_BOUNDARIES["T20_LIKE"])


if __name__ == "__main__":
    unittest.main()
