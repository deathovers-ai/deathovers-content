"""
F05 — Monte Carlo win probability beside Chase Engine (not a replacement).

Chase answers: "how often did similar historical chases recover?"
WP answers: "if remaining overs behave like this venue/format's phase
run + wicket rates, how often does the batting side win from here?"

Distributions start as format-level (and optional venue-level) phase
means/stds aggregated from venue_stats chase/1st-innings phase rates.
Wicket rates are format defaults until an event-corpus builder lands.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import (
    balls_per_over_for_match_type,
    determine_phase_from_balls,
    determine_phase_from_over,
    innings_legal_balls,
    phase_kind_for_match_type,
)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
VENUE_STATS_FILE = os.path.join(CONTEXT_DIR, "venue_stats.json")
DISTS_FILE = os.path.join(CONTEXT_DIR, "phase_distributions.json")

SCHEMA = "phase-dist-v1"
DEFAULT_N_SIMS = 1500

# Early-innings uncertainty: before this fraction of legal balls bowled.
EARLY_BALLS_FRACTION = 0.40

# ponytail: format-default wickets/over until event-built histograms exist.
# Tuned to ~6–7 wickets per T20 innings / ~8–9 per ODI, with death slightly hotter.
# Hundred borrow T20-like rates until format-specific builds exist.
DEFAULT_WICKETS_PER_OVER = {
    "T20_LIKE": {"powerplay": 0.38, "middle": 0.28, "death": 0.42},
    "ODI_LIKE": {"powerplay": 0.22, "middle": 0.16, "death": 0.28},
    "HUNDRED": {"powerplay": 0.38, "middle": 0.28, "death": 0.42},
}


def _phase_kind(match_format: str) -> str:
    return phase_kind_for_match_type(match_format)


def _max_balls(match_format: str) -> int:
    return innings_legal_balls(match_format)


def _default_wickets(match_format: str, phase: str) -> float:
    table = DEFAULT_WICKETS_PER_OVER[_phase_kind(match_format)]
    return float(table.get(phase) or table["middle"])


def _phase_block(mean: float, std: float, wickets: float, n: int) -> dict:
    return {
        "runs_per_over_mean": round(mean, 3),
        "runs_per_over_std": round(max(std, 0.5), 3),
        "wickets_per_over_mean": round(wickets, 3),
        "n": int(n),
    }


def build_phase_distributions(venue_stats: dict | None = None) -> dict:
    """Aggregate format (+ sparse venue) phase run rates from venue_stats.json."""
    if venue_stats is None:
        with open(VENUE_STATS_FILE, encoding="utf-8") as fh:
            venue_stats = json.load(fh)

    format_vals: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    venue_vals: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for venue_key, meta in venue_stats.items():
        if not isinstance(meta, dict):
            continue
        formats = meta.get("formats") or {}
        for fmt, block in formats.items():
            if not isinstance(block, dict):
                continue
            # Prefer successful-chase phase rates for chase WP; fall back to 1st innings.
            chase_phases = ((block.get("chase_phase_breakdown") or {}).get("phases") or {})
            first_phases = block.get("phase_breakdown") or {}
            for phase in ("powerplay", "middle", "death"):
                src = chase_phases.get(phase) or first_phases.get(phase) or {}
                rr = src.get("avg_run_rate")
                if rr is None:
                    continue
                rr = float(rr)
                format_vals[fmt][phase].append(rr)
                venue_vals[venue_key][fmt][phase].append(rr)

    formats_out: dict[str, dict] = {}
    for fmt, phases in format_vals.items():
        out_phases = {}
        for phase, vals in phases.items():
            if len(vals) < 3:
                continue
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            # Across-venue std understates within-match over variance; inflate.
            # ponytail: 1.8× venue-dispersion until event-level over samples exist.
            std = math.sqrt(var) * 1.8
            out_phases[phase] = _phase_block(mean, std, _default_wickets(fmt, phase), len(vals))
        if out_phases:
            formats_out[fmt] = out_phases

    venues_out: dict[str, dict] = {}
    for venue_key, by_fmt in venue_vals.items():
        venue_block = {}
        for fmt, phases in by_fmt.items():
            out_phases = {}
            for phase, vals in phases.items():
                if len(vals) < 1:
                    continue
                # Single venue usually one rate; borrow format std when thin.
                mean = sum(vals) / len(vals)
                fmt_std = (
                    (formats_out.get(fmt) or {}).get(phase) or {}
                ).get("runs_per_over_std", max(mean * 0.35, 1.5))
                out_phases[phase] = _phase_block(
                    mean, float(fmt_std), _default_wickets(fmt, phase), len(vals)
                )
            # Only publish venue override when enough format coverage at venue.
            n_blocks = sum(1 for p in out_phases.values() if p["n"] >= 1)
            if n_blocks >= 2 and (formats_out.get(fmt) or {}):
                # Gate: require venue to appear in enough format sample via chase sample
                # when available; otherwise keep format-only.
                venue_block[fmt] = out_phases
        if venue_block:
            venues_out[venue_key] = venue_block

    return {
        "schema_version": SCHEMA,
        "formats": formats_out,
        "venues": venues_out,
        "notes": (
            "runs_per_over from venue_stats chase_phase (fallback phase_breakdown); "
            "wickets_per_over are format defaults until event histograms land"
        ),
    }


def save_phase_distributions(dists: dict, path: str | None = None) -> str:
    out = path or DISTS_FILE
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(dists, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return out


def load_phase_distributions(path: str | None = None) -> dict | None:
    p = Path(path or DISTS_FILE)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema_version") != SCHEMA:
        return None
    return data


def resolve_phase_dist(
    dists: dict,
    match_format: str,
    phase: str,
    venue: str | None = None,
) -> dict | None:
    """Pick venue×format phase block, else format block. None if missing."""
    fmt = (match_format or "").upper()
    if venue:
        venue_block = ((dists.get("venues") or {}).get(venue) or {}).get(fmt) or {}
        if phase in venue_block:
            return venue_block[phase]
    fmt_block = (dists.get("formats") or {}).get(fmt) or {}
    if phase in fmt_block:
        return fmt_block[phase]
    # Soft aliases: IPL → T20, IT20 → T20, ODM → ODI
    alias = {"IPL": "T20", "IT20": "T20", "ODM": "ODI"}.get(fmt)
    if alias:
        return resolve_phase_dist(dists, alias, phase, venue=None)
    return None


def _sample_nonneg_normal(rng: random.Random, mean: float, std: float) -> float:
    # Box-style truncated normal via rejection; tiny loop, fine for MC.
    for _ in range(8):
        x = rng.gauss(mean, std)
        if x >= 0:
            return x
    return max(0.0, mean)


def _sample_poisson(rng: random.Random, lam: float) -> int:
    """Knuth Poisson; fine for λ < ~5 (wickets per over)."""
    if lam <= 0:
        return 0
    if lam > 8:
        # Normal approx for safety if someone passes a wild λ.
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= rng.random()
    return k - 1


def simulate_chase(
    state: dict,
    dists: dict,
    *,
    venue: str | None = None,
    n_sims: int = DEFAULT_N_SIMS,
    rng: random.Random | None = None,
) -> dict | None:
    """
    Monte Carlo remaining-chase outcomes from a live-chase-state-v1 dict.

    Returns None when distributions are too thin to speak.
    """
    if not state or not dists:
        return None
    if state.get("chase_complete"):
        won = int(state.get("runs_required") or 0) == 0
        return _payload(
            batting_wp=1.0 if won else 0.0,
            n_sims=0,
            uncertain=False,
            reason="chase_complete",
            state=state,
        )

    fmt = (state.get("format") or "").upper()
    target = int(state["target"])
    runs = int(state["runs"])
    wickets = int(state["wickets"])
    balls_remaining = int(state["legal_balls_remaining"])
    legal_balls = int(state["legal_balls"])

    if balls_remaining <= 0 or wickets >= 10:
        return _payload(0.0, 0, False, "no_resources", state)
    if runs >= target:
        return _payload(1.0, 0, False, "already_won", state)

    # Need at least one phase dist for this format.
    probe = resolve_phase_dist(dists, fmt, "middle", venue) or resolve_phase_dist(
        dists, fmt, "powerplay", venue
    )
    if not probe:
        return None

    rng = rng or random.Random()
    wins = 0
    # Format balls-per-over: T20/ODI stay at 6; Hundred uses 5. Never hardcode 6.
    bpo = balls_per_over_for_match_type(fmt)
    for _ in range(n_sims):
        r, w, b_left = runs, wickets, balls_remaining
        balls_bowled = legal_balls
        while b_left > 0 and w < 10 and r < target:
            phase = determine_phase_from_balls(balls_bowled, fmt)
            dist = resolve_phase_dist(dists, fmt, phase, venue) or probe
            balls_this = min(bpo, b_left)
            scale = balls_this / float(bpo)
            mean = float(dist["runs_per_over_mean"]) * scale
            std = float(dist["runs_per_over_std"]) * math.sqrt(scale)
            w_mean = float(dist["wickets_per_over_mean"]) * scale
            over_runs = int(round(_sample_nonneg_normal(rng, mean, std)))
            over_wkts = _sample_poisson(rng, w_mean)
            # Cap wickets to those remaining.
            over_wkts = min(over_wkts, 10 - w)
            r += over_runs
            w += over_wkts
            b_left -= balls_this
            balls_bowled += balls_this
            if w >= 10:
                break
        if r >= target and w < 10:
            wins += 1
        elif r >= target:
            # All-out in same over as reaching target: cricket awards the win
            # if target reached; we count win when runs hit target regardless
            # of simultaneous wicket (over-grain approximation).
            wins += 1

    batting_wp = wins / n_sims
    max_balls = _max_balls(fmt)
    uncertain = legal_balls < int(max_balls * EARLY_BALLS_FRACTION)
    return _payload(batting_wp, n_sims, uncertain, None, state)


def _payload(
    batting_wp: float,
    n_sims: int,
    uncertain: bool,
    reason: str | None,
    state: dict,
) -> dict:
    batting_wp = max(0.0, min(1.0, float(batting_wp)))
    bowling_wp = 1.0 - batting_wp
    pct = round(batting_wp * 100)
    label = (
        "LIKELY"
        if batting_wp >= 0.65
        else "LEANING"
        if batting_wp >= 0.55
        else "TOSS-UP"
        if batting_wp > 0.45
        else "LEANING AWAY"
        if batting_wp > 0.35
        else "UNLIKELY"
    )
    if uncertain and reason is None:
        label = f"EARLY · {label}"
    headline = f"Win probability {pct}% batting ({label.lower()})"
    if uncertain and reason is None:
        headline = f"Early-innings WP {pct}% — wide uncertainty"
    pointers = [
        {"label": "Batting WP", "value": round(batting_wp * 100, 1), "unit": "%"},
        {"label": "Bowling WP", "value": round(bowling_wp * 100, 1), "unit": "%"},
        {"label": "Sims", "value": n_sims, "unit": ""},
    ]
    if uncertain:
        pointers.append({"label": "Uncertainty", "value": "HIGH", "unit": ""})
    out = {
        "type": "win_probability",
        "status": "ok" if reason is None or reason in {"chase_complete", "already_won"} else reason,
        "batting_wp": round(batting_wp, 4),
        "bowling_wp": round(bowling_wp, 4),
        "n_sims": n_sims,
        "uncertain": uncertain,
        "label": label,
        "headline": headline,
        "pointers": pointers,
        "gauge": {
            "level": "LOW" if batting_wp >= 0.6 else "MODERATE" if batting_wp >= 0.4 else "HIGH",
            "batting_pct": pct,
        },
    }
    if reason:
        out["reason"] = reason
    # Echo chase snapshot keys useful to UI without nesting full state.
    out["runs_required"] = state.get("runs_required")
    out["legal_balls_remaining"] = state.get("legal_balls_remaining")
    return out


def build_win_probability_payload(
    state: dict | None,
    dists: dict | None,
    *,
    venue: str | None = None,
    n_sims: int = DEFAULT_N_SIMS,
    seed: int | None = None,
    weather_adjustment: dict | None = None,
) -> dict | None:
    """Public entry used by app.py. Silent (None) when it cannot speak."""
    if not state or not dists:
        return None
    rng = random.Random(seed) if seed is not None else random.Random()
    payload = simulate_chase(state, dists, venue=venue, n_sims=n_sims, rng=rng)
    if payload and weather_adjustment:
        payload = apply_weather_adjustment(payload, weather_adjustment)
    return payload


def apply_weather_adjustment(payload: dict, adjustment: dict) -> dict:
    """
    F09: nudge batting WP by dew delta; rain only raises uncertainty.
    Never invents DLS outcomes. Clamps to [0, 1].
    """
    if not payload or not adjustment or not adjustment.get("applied"):
        return payload
    out = dict(payload)
    delta = float(adjustment.get("batting_wp_delta") or 0.0)
    base = float(out.get("batting_wp") or 0.0)
    if delta:
        batting = max(0.0, min(1.0, base + delta))
        out["batting_wp"] = round(batting, 4)
        out["bowling_wp"] = round(1.0 - batting, 4)
        out["base_batting_wp"] = round(base, 4)
        pct = round(batting * 100)
        out["gauge"] = dict(out.get("gauge") or {})
        out["gauge"]["batting_pct"] = pct
        # Refresh pointers that carry WP %
        pointers = []
        for p in out.get("pointers") or []:
            if p.get("label") == "Batting WP":
                pointers.append({**p, "value": round(batting * 100, 1)})
            elif p.get("label") == "Bowling WP":
                pointers.append({**p, "value": round((1.0 - batting) * 100, 1)})
            else:
                pointers.append(p)
        pointers.append(
            {
                "label": "Weather adj",
                "value": f"{delta:+.0%}" if abs(delta) >= 0.01 else adjustment.get("summary", "applied"),
                "unit": "",
            }
        )
        out["pointers"] = pointers
        out["headline"] = f"Win probability {pct}% batting (weather-adjusted)"
    if adjustment.get("uncertain"):
        out["uncertain"] = True
        if "EARLY" not in (out.get("label") or ""):
            out["label"] = f"WEATHER · {out.get('label') or 'WP'}"
    out["weather_adjusted"] = True
    out["weather_summary"] = adjustment.get("summary")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build F05 phase distributions for Monte Carlo WP.")
    parser.add_argument("--venue-stats", default=VENUE_STATS_FILE)
    parser.add_argument("--out", default=DISTS_FILE)
    args = parser.parse_args(argv)
    with open(args.venue_stats, encoding="utf-8") as fh:
        venue_stats = json.load(fh)
    dists = build_phase_distributions(venue_stats)
    path = save_phase_distributions(dists, args.out)
    n_fmt = len(dists.get("formats") or {})
    n_venue = len(dists.get("venues") or {})
    print(f"Wrote {path} ({n_fmt} formats, {n_venue} venues)")
    # Self-check: easy chase should beat hard chase.
    t20 = dists["formats"].get("T20") or dists["formats"].get("IPL")
    assert t20 and "middle" in t20, "missing T20/IPL middle dist"
    easy = {
        "format": "T20",
        "target": 160,
        "runs": 140,
        "wickets": 3,
        "legal_balls": 90,
        "legal_balls_remaining": 30,
        "runs_required": 20,
        "chase_complete": False,
    }
    hard = {
        "format": "T20",
        "target": 180,
        "runs": 80,
        "wickets": 7,
        "legal_balls": 90,
        "legal_balls_remaining": 30,
        "runs_required": 100,
        "chase_complete": False,
    }
    easy_wp = simulate_chase(easy, dists, n_sims=800, rng=random.Random(1))
    hard_wp = simulate_chase(hard, dists, n_sims=800, rng=random.Random(1))
    assert easy_wp and hard_wp
    assert easy_wp["batting_wp"] > hard_wp["batting_wp"], (easy_wp, hard_wp)
    print(f"self-check ok: easy={easy_wp['batting_wp']:.2f} hard={hard_wp['batting_wp']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
