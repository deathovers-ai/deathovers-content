"""F03: context freshness helpers and stale detection."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from context_freshness import (
    STALE_AFTER_DAYS,
    build_meta,
    freshness_payload,
    infer_corpus_through_from_players,
    is_stale,
    read_context_meta,
    write_context_meta,
)


class ContextFreshnessTests(unittest.TestCase):
    def test_stale_when_older_than_threshold(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        fresh = (now - timedelta(days=STALE_AFTER_DAYS - 1)).isoformat().replace("+00:00", "Z")
        old = (now - timedelta(days=STALE_AFTER_DAYS + 1)).isoformat().replace("+00:00", "Z")
        self.assertFalse(is_stale(fresh, now=now))
        self.assertTrue(is_stale(old, now=now))
        self.assertFalse(is_stale(None, now=now))

    def test_write_and_read_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "context_meta.json")
            written = write_context_meta("2026-07-30", path=path)
            self.assertEqual(written["corpus_through"], "2026-07-30")
            self.assertTrue(written["generated_at"].endswith("Z"))
            loaded = read_context_meta(path)
            self.assertEqual(loaded["corpus_through"], "2026-07-30")

    def test_infer_corpus_through_skips_meta_key(self):
        players = {
            "_meta": {"latest_match_date": "2099-01-01"},
            "A": {"latest_match_date": "2026-01-01"},
            "B": {"latest_match_date": "2026-07-15"},
            "C": {"earliest_match_date": "2008-01-01"},
        }
        self.assertEqual(infer_corpus_through_from_players(players), "2026-07-15")

    def test_freshness_payload_marks_stale(self):
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        meta = build_meta("2026-01-01", generated_at="2026-07-01T00:00:00Z")
        meta["source"] = "test"
        payload = freshness_payload(meta, now=now)
        self.assertTrue(payload["known"])
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["corpus_through"], "2026-01-01")
        self.assertEqual(payload["stale_after_days"], 14)


if __name__ == "__main__":
    unittest.main()
