import unittest

from live_chase_bridge import build_live_chase_from_miniscore, update_first_innings_context
from live_match_context_cache import FirstInningsContextCache


FIRST = {"inningsid": 1, "runs": 180, "wickets": 6, "balls": 120}
SECOND = {"inningsid": 2, "runs": 120, "wickets": 3, "balls": 90, "target": 181}


class LiveChaseBridgeTests(unittest.TestCase):
    def test_freezes_first_innings_then_builds_chase(self):
        cache = FirstInningsContextCache()
        miniscore = {"inningsid": 2, "inningsscores": {"inningsscore": [FIRST, SECOND]}}
        context = update_first_innings_context(cache, "m1", "T20", miniscore)
        self.assertTrue(context["frozen"])
        chase = build_live_chase_from_miniscore("m1", "T20", miniscore, context)
        self.assertEqual(chase["target"], 181)
        self.assertEqual(chase["runs_required"], 61)
        self.assertEqual(chase["legal_balls_remaining"], 30)

    def test_uses_cached_target_only_when_provider_omits_it(self):
        cache = FirstInningsContextCache()
        miniscore = {"inningsid": 2, "inningsscores": {"inningsscore": [FIRST, {**SECOND, "target": None}]}}
        context = update_first_innings_context(cache, "m1", "T20", miniscore)
        chase = build_live_chase_from_miniscore("m1", "T20", miniscore, context)
        self.assertEqual(chase["target"], 181)

    def test_does_not_infer_a_target_without_cache_or_provider_target(self):
        miniscore = {"inningsid": 2, "inningsscores": {"inningsscore": [{**SECOND, "target": None}]}}
        self.assertIsNone(build_live_chase_from_miniscore("m1", "T20", miniscore, None))


if __name__ == "__main__":
    unittest.main()
