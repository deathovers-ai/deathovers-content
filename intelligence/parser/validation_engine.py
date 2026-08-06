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

# F11: format-kind thresholds. Hundred stays slightly higher until a real
# HND venue corpus lands (noisier samples). ODI slightly lower — longer
# innings make smaller relative edges more meaningful.
SIGNIFICANCE_THRESHOLD_BY_KIND = {
    "T20_LIKE": 10.0,
    "ODI_LIKE": 8.0,
    "HUNDRED": 12.0,
}


def significance_threshold_pct(match_type: str | None = None) -> float:
    """Return the significance floor for a competition / match type."""
    if not match_type:
        return SIGNIFICANCE_THRESHOLD_PCT
    try:
        from constants import UNSUPPORTED_PHASE_KIND, phase_kind_for_match_type
    except ImportError:
        return SIGNIFICANCE_THRESHOLD_PCT
    kind = phase_kind_for_match_type(match_type)
    if kind == UNSUPPORTED_PHASE_KIND:
        return SIGNIFICANCE_THRESHOLD_PCT
    return float(SIGNIFICANCE_THRESHOLD_BY_KIND.get(kind, SIGNIFICANCE_THRESHOLD_PCT))

# Venue sample floor when the explicit confidence field is absent (older
# venue_stats.json builds).
MIN_VENUE_MATCHES = 5

# F04 player enrichment floors — refuse venue/phase player insights below these.
MIN_VENUE_INNINGS = 5
MIN_PHASE_BALLS = 100

# F06 matchup floor — refuse bowler–batter insights below this legal-ball sample.
MIN_MATCHUP_BALLS = 30


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


def player_venue_is_reliable(venue_block: dict | None) -> bool:
    """Enough batting innings at this venue for a player-level comparison."""
    if not venue_block:
        return False
    batting = venue_block.get("batting") or {}
    return batting.get("innings", 0) >= MIN_VENUE_INNINGS


def player_phase_is_reliable(phase_block: dict | None) -> bool:
    """Enough balls in this phase for a player phase comparison."""
    if not phase_block:
        return False
    if "reliable" in phase_block:
        return bool(phase_block["reliable"])
    return phase_block.get("balls", 0) >= MIN_PHASE_BALLS


def matchup_is_reliable(matchup_block: dict | None) -> bool:
    """Enough legal balls between this batter and bowler for a matchup card."""
    if not matchup_block:
        return False
    if "reliable" in matchup_block:
        return bool(matchup_block["reliable"])
    return matchup_block.get("balls", 0) >= MIN_MATCHUP_BALLS
