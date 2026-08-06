"""F08: narration hard contract — numbers must come from the insight."""
import unittest

from narration_engine import (
    MAX_LLM_ATTEMPTS,
    extract_allowed_numbers,
    narrate_insight,
    narrate_insights,
    template_narration,
    validate_narration,
)


SAMPLE = {
    "type": "venue_score_comparison",
    "headline": "Score is 18% above venue average score",
    "pointers": [
        {"label": "Current Score", "value": "39/3", "unit": " (6.1 ov)"},
        {"label": "Venue Baseline", "value": 33},
        {"label": "Difference", "value": 6.0, "unit": " runs", "pct": 18.2},
        {"label": "Sample Size", "value": 42, "unit": " matches"},
    ],
}


class NarrationContractTests(unittest.TestCase):
    def test_allowlist_includes_pointer_and_headline_numbers(self):
        allowed = extract_allowed_numbers(SAMPLE)
        for token in ("39", "3", "6.1", "33", "6", "18.2", "42", "18"):
            self.assertIn(token, allowed, f"missing {token} in {allowed}")

    def test_template_always_validates(self):
        allowed = extract_allowed_numbers(SAMPLE)
        text = template_narration(SAMPLE)
        self.assertTrue(text)
        self.assertTrue(validate_narration(text, allowed))

    def test_invented_number_rejected(self):
        allowed = extract_allowed_numbers(SAMPLE)
        self.assertFalse(validate_narration("They're on 99 for 1.", allowed))

    def test_llm_accepted_when_numbers_match(self):
        draft = "At 39/3 after 6.1 ov, still 18.2% clear of the venue baseline of 33."
        out = narrate_insight(SAMPLE, llm_call=lambda _: draft)
        self.assertEqual(out["narration_source"], "llm")
        self.assertEqual(out["narration"], draft)
        # Original headline preserved
        self.assertEqual(out["headline"], SAMPLE["headline"])

    def test_llm_retries_then_template_fallback(self):
        calls = {"n": 0}

        def liar(_insight):
            calls["n"] += 1
            return "Win probability is 91% somehow."

        out = narrate_insight(SAMPLE, llm_call=liar, max_attempts=MAX_LLM_ATTEMPTS)
        self.assertEqual(calls["n"], MAX_LLM_ATTEMPTS)
        self.assertEqual(out["narration_source"], "template")
        self.assertTrue(
            validate_narration(out["narration"], extract_allowed_numbers(SAMPLE))
        )

    def test_batch_narrate_insights(self):
        results = narrate_insights([SAMPLE, "skip-me"], llm_call=lambda _: None)
        self.assertEqual(results[0]["narration_source"], "template")
        self.assertEqual(results[1], "skip-me")


if __name__ == "__main__":
    unittest.main()
