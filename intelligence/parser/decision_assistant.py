"""
F10 — Tactical Decision Assistant.

Historical-pattern recommendations for live chases. Medium confidence only.
Cites cohort / matchup / phase samples already on the match payload.
Silence when evidence is thin. Never invents recovery rates.
"""
from __future__ import annotations

DISCLAIMER = (
    "Medium-confidence historical pattern only — not an instruction to change "
    "the XI or a prediction of the result. Cite the sample; ignore when thin."
)

# Required run rate thresholds where "promote a hitter" historically matters.
# ODI lower because 50-over RRR compounds differently.
RRR_PROMOTE = {
    "T20": 9.0,
    "IT20": 9.0,
    "IPL": 9.0,
    "ODI": 6.5,
    "ODM": 6.5,
}
RRR_CONSOLIDATE_MAX = {
    "T20": 7.0,
    "IT20": 7.0,
    "IPL": 7.0,
    "ODI": 5.0,
    "ODM": 5.0,
}

MIN_BALLS_REMAINING = 12
MAX_DECISIONS = 3
CONFIDENCE = "medium"


def build_tactical_board(
    *,
    chase: dict | None,
    insights: list | None = None,
    win_probability: dict | None = None,
) -> dict | None:
    """
    Build a tactical board payload from chase + existing insights.

    Returns None when there is nothing useful to say (not a chase, or no rules fire).
    """
    decisions: list[dict] = []
    state = (chase or {}).get("state") if isinstance(chase, dict) else None
    cohort = (chase or {}).get("cohort") if isinstance(chase, dict) else None
    qualified = isinstance(chase, dict) and chase.get("status") == "qualified"

    if isinstance(state, dict) and not state.get("chase_complete"):
        promote = _promote_hitter(state, cohort if qualified else None)
        consolidate = _consolidate(state, cohort if qualified else None)
        death = _death_overs_push(state, cohort if qualified else None)
        # Death window is the more specific call; drop generic promote if both fire.
        if death:
            decisions.append(death)
        elif promote:
            decisions.append(promote)
        if consolidate:
            decisions.append(consolidate)

    insights = insights or []
    matchup = _matchup_caution(insights)
    if matchup:
        decisions.append(matchup)
    phase = _phase_form_note(insights)
    if phase:
        decisions.append(phase)

    # Prefer chase-linked decisions; keep matchup/phase as support. Cap length.
    decisions = decisions[:MAX_DECISIONS]
    if not decisions:
        return None

    return {
        "schema_version": "tactical-board-v1",
        "confidence": CONFIDENCE,
        "disclaimer": DISCLAIMER,
        "decisions": decisions,
        "win_probability": {
            "batting_wp": (win_probability or {}).get("batting_wp"),
            "label": (win_probability or {}).get("label"),
        }
        if win_probability
        else None,
    }


def _promote_hitter(state: dict, cohort: dict | None) -> dict | None:
    fmt = (state.get("format") or "").upper()
    threshold = RRR_PROMOTE.get(fmt)
    rrr = state.get("required_run_rate")
    if threshold is None or rrr is None:
        return None
    rrr = float(rrr)
    wickets = int(state.get("wickets") or 0)
    balls_left = int(state.get("legal_balls_remaining") or 0)
    if rrr < threshold or wickets > 6 or balls_left < MIN_BALLS_REMAINING:
        return None
    if wickets >= 9:
        return None

    sample = int((cohort or {}).get("sample_size") or 0)
    recovery = (cohort or {}).get("recovery_rate")
    if sample < 15 or recovery is None:
        # Need a cited cohort — refuse rather than invent.
        return None

    recovery_pct = round(float(recovery) * 100)
    return {
        "id": "promote_hitter",
        "action": "PROMOTE HITTER",
        "confidence": CONFIDENCE,
        "headline": (
            f"Required rate {rrr:.1f} exceeds {threshold:.1f} with {10 - wickets} wickets in hand — "
            f"historical chases here recovered {recovery_pct}% of the time"
        ),
        "rationale": "High RRR with resources left is the classic promote-hitter window.",
        "sample": {
            "source": "chase_cohort",
            "sample_size": sample,
            "recovery_rate": round(float(recovery), 4),
            "venue_scope": (cohort or {}).get("venue_scope"),
        },
        "pointers": [
            {"label": "RRR", "value": round(rrr, 2)},
            {"label": "Threshold", "value": threshold},
            {"label": "Wickets in hand", "value": 10 - wickets},
            {"label": "Cohort recovery", "value": recovery_pct, "unit": "%"},
            {"label": "Sample", "value": sample, "unit": " chases"},
        ],
    }


def _consolidate(state: dict, cohort: dict | None) -> dict | None:
    fmt = (state.get("format") or "").upper()
    ceiling = RRR_CONSOLIDATE_MAX.get(fmt)
    rrr = state.get("required_run_rate")
    if ceiling is None or rrr is None:
        return None
    rrr = float(rrr)
    wickets = int(state.get("wickets") or 0)
    pace_gap = (cohort or {}).get("pace_gap_runs")
    # Ahead of successful pace (positive gap) and RRR under control.
    if rrr > ceiling or pace_gap is None or float(pace_gap) < 5 or wickets >= 7:
        return None
    sample = int((cohort or {}).get("sample_size") or 0)
    if sample < 15:
        return None

    return {
        "id": "consolidate",
        "action": "CONSOLIDATE",
        "confidence": CONFIDENCE,
        "headline": (
            f"RRR {rrr:.1f} is manageable and the chase is "
            f"{float(pace_gap):+.0f} runs ahead of successful pace"
        ),
        "rationale": "When ahead of the successful cohort pace, preserve wickets over forced acceleration.",
        "sample": {
            "source": "chase_cohort",
            "sample_size": sample,
            "pace_gap_runs": round(float(pace_gap), 1),
            "venue_scope": (cohort or {}).get("venue_scope"),
        },
        "pointers": [
            {"label": "RRR", "value": round(rrr, 2)},
            {"label": "Pace gap", "value": round(float(pace_gap), 1), "unit": " runs"},
            {"label": "Sample", "value": sample, "unit": " chases"},
        ],
    }


def _death_overs_push(state: dict, cohort: dict | None) -> dict | None:
    fmt = (state.get("format") or "").upper()
    balls_left = int(state.get("legal_balls_remaining") or 0)
    # Last 5 overs (T20) / last 10 overs (ODI) roughly.
    death_balls = 30 if fmt in {"ODI", "ODM"} else 30
    if balls_left > death_balls or balls_left < 6:
        return None
    rrr = state.get("required_run_rate")
    threshold = RRR_PROMOTE.get(fmt)
    if rrr is None or threshold is None or float(rrr) < threshold:
        return None
    sample = int((cohort or {}).get("sample_size") or 0)
    recovery = (cohort or {}).get("recovery_rate")
    if sample < 15 or recovery is None:
        return None
    # Avoid duplicating promote_hitter if both would fire — death is more specific.
    return {
        "id": "death_push",
        "action": "DEATH OVERS PUSH",
        "confidence": CONFIDENCE,
        "headline": (
            f"{balls_left} balls left at RRR {float(rrr):.1f} — "
            f"similar death chases finished at {round(float(recovery) * 100)}% recovery"
        ),
        "rationale": "Late high-RRR window: maximize boundary options with remaining wickets.",
        "sample": {
            "source": "chase_cohort",
            "sample_size": sample,
            "recovery_rate": round(float(recovery), 4),
            "venue_scope": (cohort or {}).get("venue_scope"),
        },
        "pointers": [
            {"label": "Balls left", "value": balls_left},
            {"label": "RRR", "value": round(float(rrr), 2)},
            {"label": "Cohort recovery", "value": round(float(recovery) * 100), "unit": "%"},
            {"label": "Sample", "value": sample, "unit": " chases"},
        ],
    }


def _matchup_caution(insights: list) -> dict | None:
    for insight in insights:
        if not isinstance(insight, dict) or insight.get("type") != "bowler_batter_matchup":
            continue
        sr = _pointer_number(insight, ("Strike Rate", "SR", "Historical SR", "Batter SR"))
        balls = _pointer_number(insight, ("Balls", "Sample", "balls"))
        dismissals = _pointer_number(insight, ("Dismissals", "dismissals"))
        if sr is None:
            continue
        # Caution when SR is poor (<120) or multiple dismissals.
        if sr >= 120 and (dismissals or 0) < 2:
            continue
        sample_balls = int(balls or 0)
        if sample_balls < 30:
            continue
        return {
            "id": "matchup_caution",
            "action": "MATCHUP CAUTION",
            "confidence": CONFIDENCE,
            "headline": insight.get("headline") or "Live batter–bowler matchup is historically tough",
            "rationale": "F06 matchup sample suggests this pairing has suppressed scoring or taken wickets.",
            "sample": {
                "source": "matchup_stats",
                "sample_size": sample_balls,
                "strike_rate": sr,
                "dismissals": dismissals,
            },
            "pointers": insight.get("pointers") or [],
        }
    return None


def _phase_form_note(insights: list) -> dict | None:
    for insight in insights:
        if not isinstance(insight, dict) or insight.get("type") != "player_phase_mismatch":
            continue
        diff = insight.get("diff_pct")
        if diff is None or float(diff) > -SIGNIFICANCE_FLOOR:
            continue
        balls = _pointer_number(insight, ("Phase Sample", "Sample", "balls"))
        if balls is not None and balls < 100:
            continue
        return {
            "id": "phase_form",
            "action": "PHASE FORM CHECK",
            "confidence": CONFIDENCE,
            "headline": insight.get("headline") or "Batter is below their phase baseline",
            "rationale": "F04 phase history shows underperformance in this window — consider a hitter if RRR climbs.",
            "sample": {
                "source": "player_phase",
                "sample_size": int(balls or 0),
                "diff_pct": float(diff),
            },
            "pointers": insight.get("pointers") or [],
        }
    return None


SIGNIFICANCE_FLOOR = 10.0  # align with insight significance threshold


def _pointer_number(insight: dict, labels: tuple[str, ...]) -> float | None:
    for pointer in insight.get("pointers") or []:
        if not isinstance(pointer, dict):
            continue
        if pointer.get("label") in labels:
            try:
                return float(pointer.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def build_tactical_board_from_shaped(shaped: dict | None) -> dict | None:
    """Convenience for app.py — read chase / insights / WP off a shaped match payload."""
    if not shaped:
        return None
    intel = shaped.get("intelligence") or {}
    return build_tactical_board(
        chase=shaped.get("chase"),
        insights=intel.get("insights") if isinstance(intel, dict) else None,
        win_probability=shaped.get("win_probability"),
    )
