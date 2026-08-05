"""
F06 — Bowler–batter matchup matrix.

Builds sparse matchup_stats.json from ball events:
  batter -> bowler -> {
    balls, runs, dismissals, dismissal_kinds,
    venues, years, strike_rate, average, reliable
  }

Only pairs with >= MIN_MATCHUP_BALLS legal balls are written (sparse).
Identity merges only via player_aliases.json (same rule as player_context).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_freshness import write_context_meta
from context_repository import normalize_venue
from player_context import (
    EVENTS_DIR,
    MANIFEST,
    canonical_name,
    competition_code_for_match,
    load_aliases,
)
from validation_engine import MIN_MATCHUP_BALLS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
MATCHUP_STATS_FILE = os.path.join(CONTEXT_DIR, "matchup_stats.json")

# Product slice for this ship (same as F04 enrichment): T20-like only.
MATCHUP_FORMATS = {"T20", "IT20", "IPL"}

# Prefer this order when formatting "2 lbw + 2 caught" style summaries.
_KIND_ORDER = (
    "caught", "bowled", "lbw", "stumped", "caught and bowled",
    "hit wicket", "obstructing the field", "retired hurt", "hit the ball twice",
)


def _empty_pair():
    return {
        "balls": 0,
        "runs": 0,
        "dismissals": 0,
        "dismissal_kinds": defaultdict(int),
        "venues": defaultdict(int),  # venue_key -> balls faced there
        "years": set(),
    }


def format_dismissal_kinds(kinds: dict | None) -> str | None:
    """Turn {lbw: 2, caught: 2} into '2 lbw + 2 caught'. None if empty."""
    if not kinds:
        return None
    parts = []
    seen = set()
    for kind in _KIND_ORDER:
        n = int(kinds.get(kind) or 0)
        if n:
            parts.append(f"{n} {kind}")
            seen.add(kind)
    for kind, n in sorted(kinds.items()):
        if kind in seen:
            continue
        n = int(n or 0)
        if n:
            parts.append(f"{n} {kind}")
    return " + ".join(parts) if parts else None


def format_years(years: list | None) -> str | None:
    """[2017, 2021, 2022] -> '2017–2025' or '2017, 2021' when sparse."""
    if not years:
        return None
    ys = sorted(int(y) for y in years)
    if len(ys) == 1:
        return str(ys[0])
    # Contiguous span → en-dash range; otherwise list.
    if ys[-1] - ys[0] + 1 == len(ys):
        return f"{ys[0]}\u2013{ys[-1]}"
    if len(ys) <= 4:
        return ", ".join(str(y) for y in ys)
    return f"{ys[0]}\u2013{ys[-1]} ({len(ys)} seasons)"


def format_venues(venues: dict | None, limit: int = 3) -> str | None:
    """Top venues by balls, e.g. 'Wankhede Stadium (18), Brabourne (5)'."""
    if not venues:
        return None
    ranked = sorted(venues.items(), key=lambda kv: (-kv[1], kv[0]))
    top = ranked[:limit]
    parts = [f"{name} ({balls})" for name, balls in top]
    extra = len(ranked) - len(top)
    if extra > 0:
        parts.append(f"+{extra} more")
    return ", ".join(parts)


def _finalize_pair(raw: dict) -> dict:
    balls = raw["balls"]
    dismissals = raw["dismissals"]
    kinds = {k: int(v) for k, v in sorted((raw.get("dismissal_kinds") or {}).items()) if v}
    venues = {
        k: int(v)
        for k, v in sorted(
            (raw.get("venues") or {}).items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
        if v
    }
    years = sorted(int(y) for y in (raw.get("years") or set()))
    return {
        "balls": balls,
        "runs": raw["runs"],
        "dismissals": dismissals,
        "dismissal_kinds": kinds,
        "venues": venues,
        "years": years,
        "strike_rate": round((raw["runs"] / balls) * 100, 2) if balls else 0.0,
        "average": round(raw["runs"] / dismissals, 2) if dismissals else None,
        "reliable": balls >= MIN_MATCHUP_BALLS,
    }


def build_matchup_stats(
    events_dir: str = EVENTS_DIR,
    manifest_path: str = MANIFEST,
    out_path: str = MATCHUP_STATS_FILE,
    formats: set[str] | None = None,
):
    formats = formats or MATCHUP_FORMATS
    aliases = load_aliases()
    print(
        f"Loaded {len(aliases)} confirmed name aliases."
        if aliases else
        "No player_aliases.json — using raw names."
    )

    manifest_by_id = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            for row in json.load(f):
                manifest_by_id[str(row["match_id"])] = row

    if os.path.isdir(events_dir) and any(n.endswith(".json") for n in os.listdir(events_dir)):
        paths = [
            os.path.join(events_dir, n)
            for n in os.listdir(events_dir)
            if n.endswith(".json")
        ]
    else:
        raise SystemExit(f"No event files in {events_dir}")

    # batter -> bowler -> counters
    pairs: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(_empty_pair))
    corpus_through = None
    matches_used = 0

    for i, path in enumerate(sorted(paths), 1):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("meta") or {}
        match_id = str(meta.get("match_id") or os.path.splitext(os.path.basename(path))[0])
        man = manifest_by_id.get(match_id) or {}
        code = competition_code_for_match(meta, man.get("competition_code"))
        if code not in formats:
            continue
        matches_used += 1
        dates = meta.get("dates") or []
        match_year = None
        if dates:
            d = dates[-1]
            if corpus_through is None or d > corpus_through:
                corpus_through = d
            try:
                match_year = int(str(d)[:4])
            except ValueError:
                match_year = None
        venue_key = normalize_venue(meta["venue"]) if meta.get("venue") else None

        for event in data.get("events") or []:
            batter = canonical_name(event["batter"], aliases)
            bowler = canonical_name(event["bowler"], aliases)
            # Same batter-facing rule as player_context: wides do not face the batter.
            if event.get("extra_type") != "wides":
                cell = pairs[batter][bowler]
                cell["balls"] += 1
                cell["runs"] += int(event.get("runs_batter") or 0)
                if venue_key:
                    cell["venues"][venue_key] += 1
                if match_year is not None:
                    cell["years"].add(match_year)

            if event.get("is_wicket"):
                cell = pairs[batter][bowler]
                for w in event.get("wickets") or []:
                    out = canonical_name(w.get("player_out") or batter, aliases)
                    # Credit bowler dismissals only (run outs are not bowler wickets).
                    if out == batter and w.get("kind") not in ("run out",):
                        kind = (w.get("kind") or "unknown").strip().lower() or "unknown"
                        cell["dismissals"] += 1
                        cell["dismissal_kinds"][kind] += 1
                        break

        if i % 1000 == 0:
            print(f"  scanned {i}/{len(paths)} event files...")

    # Sparse write: only reliable pairs.
    out: dict[str, dict[str, dict]] = {}
    pair_count = 0
    for batter, bowlers in pairs.items():
        sparse = {}
        for bowler, raw in bowlers.items():
            if raw["balls"] < MIN_MATCHUP_BALLS:
                continue
            sparse[bowler] = _finalize_pair(raw)
            pair_count += 1
        if sparse:
            out[batter] = sparse

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    meta = write_context_meta(corpus_through)
    print(
        f"Wrote {pair_count} matchup pairs across {len(out)} batters "
        f"(min balls={MIN_MATCHUP_BALLS}) from {matches_used} matches → {out_path}"
    )
    print(f"context_meta: {meta}")
    return out


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Build sparse bowler–batter matchup stats.")
    cli.add_argument("--out", default=MATCHUP_STATS_FILE)
    cli.add_argument("--events-dir", default=EVENTS_DIR)
    cli.add_argument("--manifest", default=MANIFEST)
    args = cli.parse_args()
    build_matchup_stats(events_dir=args.events_dir, manifest_path=args.manifest, out_path=args.out)
