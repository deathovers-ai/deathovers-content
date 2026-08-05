"""
Validation Engine — data-confidence guards for insights.

Decides whether we are allowed to speak. Insight generation lives in
insight_engine.py and must only narrate facts that pass these guards.

HARD RULE (see DATA_QUALITY_NOTES.md / insight_engine history):
refuse comparisons against player or venue data we have not validated
as reliable. Silence is correct; degraded-confidence insights are not.
"""

# Widened safety margin: refuse comparisons for any player whose earliest
# recorded match falls before this date. Deliberately later than the
# corpus's real coverage start (~2003) because earliest_match_date cannot
# distinguish "debuted in 2003" from "career started earlier, Cricsheet
# just doesn't have it" (Kallis case). False refusals over false inclusions.
DATA_CONFIDENCE_CUTOFF = "2005-01-01"

# Minimum divergence from historical average before an insight is worth
# emitting. Below this, silence — commenting on every wobble is noise.
SIGNIFICANCE_THRESHOLD_PCT = 10.0

# Venue sample floor when the explicit confidence field is absent (older
# venue_stats.json builds).
MIN_VENUE_MATCHES = 5


class DataConfidenceError(Exception):
    """Raised when an insight was about to be generated from unvalidated
    (pre-cutoff) data. Callers should catch this and skip the insight,
    not surface a degraded-confidence version of it."""
    pass


def venue_data_is_reliable(venue_entry, match_type):
    """
    Venue reliability check: enough matches in this format at this venue?

    Prefers the explicit "confidence" field from context_repository when
    present; falls back to MIN_VENUE_MATCHES for older venue_stats.json.
    """
    fmt = venue_entry.get("formats", {}).get(match_type)
    if not fmt:
        return False
    if "confidence" in fmt:
        return fmt["confidence"] in ("high", "medium")
    return fmt.get("matches_with_data", 0) >= MIN_VENUE_MATCHES


def player_data_is_reliable(player_entry):
    """
    Refuse comparisons for players whose earliest recorded match predates
    the confirmed-reliable coverage window.
    """
    earliest = player_entry.get("earliest_match_date")
    if earliest is None:
        return False
    return earliest >= DATA_CONFIDENCE_CUTOFF
