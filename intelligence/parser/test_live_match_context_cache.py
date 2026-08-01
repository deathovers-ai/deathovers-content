from datetime import datetime, timedelta, timezone
import unittest

from live_match_context_cache import FirstInningsContextCache


class MutableClock:
    def __init__(self):
        self.value = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


def snapshot(**overrides):
    value = {
        "innings": 1,
        "runs": 184,
        "wickets": 6,
        "legal_balls": 120,
        "target": 185,
        "is_complete": True,
    }
    value.update(overrides)
    return value


class FirstInningsContextCacheTests(unittest.TestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.cache = FirstInningsContextCache(timedelta(minutes=5), now=self.clock)

    def test_freeze_prevents_later_updates_and_read_is_a_copy(self):
        self.cache.upsert("m1", snapshot())
        frozen = self.cache.freeze("m1")
        self.assertTrue(frozen["frozen"])

        self.cache.upsert("m1", snapshot(runs=190, target=191))
        loaded = self.cache.get("m1")
        self.assertEqual(loaded["snapshot"]["runs"], 184)
        loaded["snapshot"]["runs"] = 0
        self.assertEqual(self.cache.get("m1")["snapshot"]["runs"], 184)

    def test_entry_expires_and_is_removed(self):
        self.cache.upsert("m1", snapshot())
        self.clock.value += timedelta(minutes=5)
        self.assertIsNone(self.cache.get("m1"))

    def test_incomplete_snapshot_cannot_freeze(self):
        self.cache.upsert("m1", snapshot(is_complete=False))
        with self.assertRaises(ValueError):
            self.cache.freeze("m1")

    def test_invalid_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cache.upsert("m1", snapshot(innings=2))
        with self.assertRaises(ValueError):
            self.cache.upsert("m1", snapshot(target=184))


if __name__ == "__main__":
    unittest.main()
