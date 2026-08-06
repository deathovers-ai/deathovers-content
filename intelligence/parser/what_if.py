"""
F12 — Historical / scenario What-If on replay_engine + F05 Monte Carlo.

Fork a chase state, resimulate remaining overs, compare baseline WP vs fork WP.
When event files exist, can also replay to a point and attach the actual final.

XI rule: batting_order may only name players from the provided XI (≤11).
"""
from __future__ import annotations

import os
from typing import Any

from chase_state import FORMAT_BALL_LIMITS, build_chase_state, cricket_overs_to_legal_balls
from win_probability import DEFAULT_N_SIMS, build_win_probability_payload, load_phase_distributions

DISCLAIMER = (
    "Simulation only — venue/format phase rates, not a prediction of the real match. "
    "Actual outcomes can differ widely. Not for betting or integrity claims."
)

EVENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output",
    "events",
)


class WhatIfError(ValueError):
    """User-facing validation error for What-If requests."""


def validate_xi(xi: list[str] | None, batting_order: list[str] | None) -> dict:
    """Enforce ≤11 XI and batting_order ⊆ XI. Empty lists are fine."""
    xi_list = _clean_names(xi)
    order = _clean_names(batting_order)
    if len(xi_list) > 11:
        raise WhatIfError("XI may contain at most 11 players")
    if order and not xi_list:
        raise WhatIfError("batting_order requires an XI")
    xi_set = {n.casefold(): n for n in xi_list}
    for name in order:
        if name.casefold() not in xi_set:
            raise WhatIfError(f"batting_order player not in XI: {name}")
    # Dedup case-insensitive while preserving first spelling.
    if len(xi_set) != len(xi_list):
        raise WhatIfError("XI contains duplicate players")
    return {"xi": xi_list, "batting_order": order}


def _clean_names(names: list[str] | None) -> list[str]:
    out = []
    for n in names or []:
        s = " ".join(str(n).split())
        if s:
            out.append(s)
    return out


def state_from_scoreboard(
    *,
    match_format: str,
    target: int,
    runs: int,
    wickets: int,
    overs: str | float | int | None = None,
    legal_balls: int | None = None,
    match_id: str = "what-if",
) -> dict:
    """Build a live-chase-state-v1 from scoreboard inputs."""
    fmt = (match_format or "").upper()
    if fmt not in FORMAT_BALL_LIMITS:
        raise WhatIfError(f"unsupported format: {match_format}")
    if legal_balls is None:
        if overs is None:
            raise WhatIfError("overs or legal_balls required")
        legal_balls = cricket_overs_to_legal_balls(overs)
    return build_chase_state(
        match_id=str(match_id or "what-if"),
        match_format=fmt,
        runs=int(runs),
        wickets=int(wickets),
        legal_balls=int(legal_balls),
        target=int(target),
    )


def apply_fork(baseline: dict, fork: dict | None) -> dict:
    """
    Apply fork overrides onto baseline scoreboard facts, then rebuild state.

    Allowed keys: runs, wickets, legal_balls, overs, target, format.
    """
    fork = fork or {}
    allowed = {"runs", "wickets", "legal_balls", "overs", "target", "format", "match_format"}
    unknown = set(fork) - allowed
    if unknown:
        raise WhatIfError(f"unsupported fork keys: {sorted(unknown)}")

    fmt = (fork.get("format") or fork.get("match_format") or baseline.get("format") or "").upper()
    runs = int(fork["runs"]) if "runs" in fork else int(baseline["runs"])
    wickets = int(fork["wickets"]) if "wickets" in fork else int(baseline["wickets"])
    target = int(fork["target"]) if "target" in fork else int(baseline["target"])
    if "legal_balls" in fork:
        legal_balls = int(fork["legal_balls"])
    elif "overs" in fork:
        legal_balls = cricket_overs_to_legal_balls(fork["overs"])
    else:
        legal_balls = int(baseline["legal_balls"])

    return build_chase_state(
        match_id=str(baseline.get("match_id") or "what-if"),
        match_format=fmt,
        runs=runs,
        wickets=wickets,
        legal_balls=legal_balls,
        target=target,
    )


def replay_baseline(
    match_id: str,
    *,
    innings: int = 2,
    over: int,
    ball_in_over: int = 0,
    events_dir: str = EVENTS_DIR,
) -> tuple[dict, dict | None]:
    """
    Replay a stored match to (innings, over, ball) and return chase state + actual final.

    Returns (state, actual) where actual is {final_runs, final_wickets, chase_won, batting_team}
    when the match has a usable second-innings chase. Raises WhatIfError if events missing.
    """
    path = os.path.join(events_dir, f"{match_id}.json")
    if not os.path.isfile(path):
        raise WhatIfError(f"match events not available: {match_id}")

    from replay_engine import ReplayEngine

    engine = ReplayEngine(match_id, events_dir=events_dir)
    snap = engine.replay_to(innings, over, ball_in_over)
    if not snap:
        raise WhatIfError("replay produced no state at that point")

    meta = engine.meta or {}
    match_type = (meta.get("match_type") or meta.get("competition_code") or "T20").upper()
    if match_type not in FORMAT_BALL_LIMITS:
        # Competition codes like IPL are supported; unknown → reject.
        comp = (meta.get("competition_code") or "").upper()
        match_type = comp if comp in FORMAT_BALL_LIMITS else match_type
    if match_type not in FORMAT_BALL_LIMITS:
        raise WhatIfError(f"unsupported match format for What-If: {match_type}")

    finals = engine.final_state()
    first = finals.get(1) or {}
    second = finals.get(2) or {}
    if innings != 2 or not first or not second:
        raise WhatIfError("What-If historical mode requires a second-innings chase")

    target = int(first.get("score") or 0) + 1
    state = build_chase_state(
        match_id=str(match_id),
        match_format=match_type,
        runs=int(snap["score"]),
        wickets=int(snap["wickets"]),
        legal_balls=int(snap["legal_balls_bowled"]),
        target=target,
    )

    batting_team = second.get("batting_team")
    outcome = meta.get("outcome") or {}
    chase_won = outcome.get("winner") == batting_team
    actual = {
        "final_runs": int(second.get("score") or 0),
        "final_wickets": int(second.get("wickets") or 0),
        "chase_won": bool(chase_won),
        "batting_team": batting_team,
        "target": target,
        "fork_point": {
            "innings": innings,
            "over": over,
            "ball_in_over": ball_in_over,
            "score": f"{snap['score']}/{snap['wickets']}",
            "overs": snap.get("overs"),
        },
    }
    return state, actual


def run_what_if(
    *,
    baseline: dict,
    fork: dict | None = None,
    dists: dict | None = None,
    venue: str | None = None,
    xi: list[str] | None = None,
    batting_order: list[str] | None = None,
    n_sims: int = DEFAULT_N_SIMS,
    seed: int | None = 42,
    actual: dict | None = None,
) -> dict:
    """
    Compare Monte Carlo WP for baseline chase vs forked chase.

    `baseline` is a live-chase-state-v1 dict (or build via state_from_scoreboard).
    """
    xi_info = validate_xi(xi, batting_order)
    if dists is None:
        dists = load_phase_distributions()
    if not dists:
        raise WhatIfError("phase distributions unavailable")

    forked = apply_fork(baseline, fork)
    base_wp = build_win_probability_payload(
        baseline, dists, venue=venue, n_sims=n_sims, seed=seed
    )
    fork_wp = build_win_probability_payload(
        forked, dists, venue=venue, n_sims=n_sims, seed=seed
    )
    if not base_wp or not fork_wp:
        raise WhatIfError("insufficient phase data to simulate this format/venue")

    delta = round(float(fork_wp["batting_wp"]) - float(base_wp["batting_wp"]), 4)
    out: dict[str, Any] = {
        "schema_version": "what-if-v1",
        "baseline": {"state": baseline, "win_probability": base_wp},
        "simulated": {"state": forked, "win_probability": fork_wp},
        "comparison": {
            "batting_wp_delta": delta,
            "batting_wp_delta_pp": round(delta * 100, 1),
            "headline": _comparison_headline(base_wp, fork_wp, delta),
        },
        "xi": xi_info["xi"],
        "batting_order": xi_info["batting_order"],
        "venue": venue,
        "disclaimer": DISCLAIMER,
        "n_sims": n_sims,
    }
    if actual:
        out["actual"] = actual
        # Did the real chase win, and how does baseline WP relate?
        out["comparison"]["actual_chase_won"] = bool(actual.get("chase_won"))
        out["comparison"]["baseline_said_favorite"] = float(base_wp["batting_wp"]) >= 0.5
    return out


def _comparison_headline(base_wp: dict, fork_wp: dict, delta: float) -> str:
    base_pct = round(float(base_wp["batting_wp"]) * 100)
    fork_pct = round(float(fork_wp["batting_wp"]) * 100)
    if abs(delta) < 0.01:
        return f"Fork barely moves WP ({base_pct}% → {fork_pct}%)"
    direction = "helps" if delta > 0 else "hurts"
    return f"Fork {direction} batting side: {base_pct}% → {fork_pct}% ({delta * 100:+.1f} pp)"


def run_what_if_request(payload: dict, dists: dict | None = None) -> dict:
    """Parse a JSON API body into a What-If result."""
    if not isinstance(payload, dict):
        raise WhatIfError("body must be a JSON object")

    actual = None
    baseline = payload.get("baseline")
    if payload.get("match_id") and payload.get("over") is not None:
        baseline, actual = replay_baseline(
            str(payload["match_id"]),
            innings=int(payload.get("innings") or 2),
            over=int(payload["over"]),
            ball_in_over=int(payload.get("ball_in_over") or payload.get("ball") or 0),
        )
    elif isinstance(baseline, dict) and "legal_balls_remaining" in baseline and "target" in baseline:
        # Already a chase state.
        pass
    elif isinstance(baseline, dict):
        baseline = state_from_scoreboard(
            match_format=baseline.get("format") or baseline.get("match_format") or "T20",
            target=int(baseline["target"]),
            runs=int(baseline["runs"]),
            wickets=int(baseline["wickets"]),
            overs=baseline.get("overs"),
            legal_balls=baseline.get("legal_balls"),
            match_id=str(baseline.get("match_id") or "what-if"),
        )
    else:
        raise WhatIfError("baseline scoreboard or match_id+over required")

    n_sims = int(payload.get("n_sims") or DEFAULT_N_SIMS)
    n_sims = max(100, min(n_sims, 5000))
    seed = payload.get("seed", 42)
    if seed is not None:
        seed = int(seed)

    return run_what_if(
        baseline=baseline,
        fork=payload.get("fork"),
        dists=dists,
        venue=payload.get("venue"),
        xi=payload.get("xi"),
        batting_order=payload.get("batting_order"),
        n_sims=n_sims,
        seed=seed,
        actual=actual,
    )
