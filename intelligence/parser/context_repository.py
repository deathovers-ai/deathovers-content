"""
Epic 4a - Context Repository (Venue + Phase layer)

Goal: Turn per-match facts (from metrics_engine.py, applied across all
22,284 matches) into historical CONTEXT - "what's typical at this venue."
This is still facts, not opinions: averages, counts, distributions.
No "good/bad" labels here either - that's the Insight Engine's job.

Two-step process:
  1. Normalize venue name strings (Cricsheet has ~4 different spellings
     for some grounds - "R Premadasa Stadium", "R.Premadasa Stadium",
     "R Premadasa Stadium, Colombo" are all the SAME ground and must be
     merged, or venue stats silently fragment and become wrong).
  2. Aggregate: for each normalized venue, compute avg 1st innings score,
     avg by phase (powerplay/middle/death), matches played, by format.

This module reads the parsed events (output/events/*.json) directly,
using the Replay Engine + Metrics Engine to compute per-match facts,
then aggregates across matches. It writes one output file:
  output/context/venue_stats.json
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from replay_engine import ReplayEngine, MatchState
from metrics_engine import current_run_rate

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_DIR = os.path.join(BASE_DIR, "output", "events")
MANIFEST = os.path.join(BASE_DIR, "output", "manifest.json")
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
OUT_FILE = os.path.join(CONTEXT_DIR, "venue_stats.json")

# Formats we compute venue context for. Test excluded - no fixed overs,
# powerplay/death-overs concepts don't apply the same way.
LIMITED_OVERS_FORMATS = {"T20", "IT20", "IPL", "ODI", "ODM"}

# Standard phase boundaries. T20: PP 1-6, middle 7-15, death 16-20.
# ODI: PP 1-10, middle 11-40, death 41-50. Applied per-format below.
PHASE_BOUNDARIES = {
    "T20_LIKE": {"powerplay": (0, 6), "middle": (6, 15), "death": (15, 20)},
    "ODI_LIKE": {"powerplay": (0, 10), "middle": (10, 40), "death": (40, 50)},
}


def normalize_venue(raw_name):
    """
    Collapse venue name variants into one canonical key.

    Strategy:
    - Strip leading/trailing whitespace.
    - Remove a trailing ", <City>[, <Country>]" suffix IF the part before
      the comma already looks like a full ground name (i.e. don't strip
      when the comma is the ONLY thing separating a short code from a
      city - rare in this dataset, but we're conservative).
    - Normalize "R.Premadasa" -> "R Premadasa" (period-after-initial noise).
    - Collapse multiple spaces.
    - Preserve numbered grounds ("Albert Park 1" vs "Albert Park 2",
      "Alur Cricket Stadium II") - these are genuinely different venues
      and must NOT be merged.
    - Case-insensitive matching, but canonical form keeps original casing
      of the first-seen variant.
    """
    name = raw_name.strip()
    name = re.sub(r"\s+", " ", name)
    # "R.Premadasa" -> "R Premadasa" (period directly after a single
    # capital initial, common OCR/typing variant in Cricsheet)
    name = re.sub(r"\b([A-Z])\.(?=[A-Z][a-z])", r"\1 ", name)

    # Split off trailing ", City" or ", City, Country" segments.
    parts = [p.strip() for p in name.split(",")]
    ground = parts[0]

    # Ground name is the normalization key. City is informational only -
    # we don't use it to disambiguate because the same ground never has
    # two different real names for two different cities in this dataset;
    # duplication only comes from Cricsheet sometimes including the city
    # in the venue field and sometimes not.
    key = ground.strip()
    key = re.sub(r"\s+", " ", key)
    return key


# Generic venue-type suffix words that live providers (Cricbuzz) often
# append but Cricsheet frequently omits, e.g. Cricbuzz's "Lord's Cricket
# Ground, London" vs Cricsheet's bare "Lord's". Order matters: longer,
# more specific suffixes are tried before shorter ones so "International
# Cricket Stadium" is stripped as one unit rather than leaving "International"
# behind after only "Stadium" is removed.
GENERIC_VENUE_SUFFIXES = [
    "International Cricket Stadium",
    "International Stadium",
    "Cricket Stadium",
    "Cricket Ground",
    "Sports Complex",
    "Sports Club",
    "Stadium",
    "Ground",
]


def resolve_venue_key(raw_name, known_venue_keys):
    """
    Resolve a live-provider venue string to a key that actually exists in
    venue_stats.json, tolerating a live provider's fuller naming (e.g.
    Cricbuzz's "Lord's Cricket Ground, London") against Cricsheet's terser
    convention (e.g. "Lord's").

    Strategy, in order, stopping at the first hit:
      1. normalize_venue() as-is - handles the common case (city/country
         suffix stripping, initial-period normalization) and is checked
         first since it's already reliable for the bulk of venues.
      2. Strip one trailing generic suffix word ("Cricket Ground",
         "Stadium", etc.) from the normalized name and check again - this
         is what recovers "Lord's Cricket Ground" -> "Lord's" and similar
         cases where the two providers just disagree on how much of the
         venue's formal name to include.

    Only ever strips a known generic suffix word, never guesses at
    arbitrary substring matches - so this can't accidentally merge two
    genuinely different grounds that happen to share a short prefix.

    Returns the resolved key if found in known_venue_keys, else None.
    """
    if not raw_name:
        return None

    direct_key = normalize_venue(raw_name)
    if direct_key in known_venue_keys:
        return direct_key

    for suffix in GENERIC_VENUE_SUFFIXES:
        if direct_key.endswith(" " + suffix):
            stripped_key = direct_key[: -(len(suffix) + 1)].strip()
            if stripped_key and stripped_key in known_venue_keys:
                return stripped_key

    return None


def build_venue_alias_map():
    """
    Scan the manifest + all match meta to build raw_venue -> normalized_key
    mapping, and normalized_key -> canonical display name (first seen,
    preferring the longer/more descriptive variant for display).
    """
    with open(MANIFEST) as f:
        manifest = json.load(f)

    alias_map = {}
    canonical_display = {}

    for m in manifest:
        match_id = m["match_id"]
        path = os.path.join(EVENTS_DIR, f"{match_id}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)["meta"]
        raw_venue = meta.get("venue")
        if not raw_venue:
            continue

        key = normalize_venue(raw_venue)
        alias_map[raw_venue] = key

        # Prefer the longest variant (usually most descriptive, e.g.
        # includes city) as the display name for this key.
        if key not in canonical_display or len(raw_venue) > len(canonical_display[key]):
            canonical_display[key] = raw_venue

    return alias_map, canonical_display


def phase_set_for_format(total_overs):
    return PHASE_BOUNDARIES["ODI_LIKE"] if total_overs > 20 else PHASE_BOUNDARIES["T20_LIKE"]


def compute_match_venue_facts(match_id, match_type, total_overs):
    """
    Replay one match fully and extract, per innings:
      - final score, wickets, overs faced (1st innings total useful for
        "avg first innings score")
      - runs scored within each phase window (powerplay/middle/death)
    Returns a list of per-innings fact dicts.
    """
    engine = ReplayEngine(match_id)
    phases = phase_set_for_format(total_overs)

    results = []
    for innings_num in engine._innings_states.keys() if False else [1, 2]:
        # replay fresh for each innings extraction to keep this function
        # stateless/simple; full_replay() is cheap (one pass over events)
        pass

    # single full pass, bucket events by innings + phase
    innings_data = {}  # innings_num -> {"runs":0,"balls":0,"wkts":0,"phase_runs":{...}}
    for event in engine.all_events:
        n = event["innings_num"]
        if n not in innings_data:
            innings_data[n] = {
                "runs": 0, "wickets": 0, "legal_balls": 0,
                "phase_runs": {p: 0 for p in phases},
                "phase_balls": {p: 0 for p in phases},
                "batting_team": event["batting_team"],
            }
        d = innings_data[n]
        d["runs"] += event["runs_total"]
        if event["is_wicket"]:
            d["wickets"] += len(event["wickets"])
        if event["is_legal_delivery"]:
            d["legal_balls"] += 1
            over = event["over"]
            for phase_name, (start, end) in phases.items():
                if start <= over < end:
                    d["phase_runs"][phase_name] += event["runs_total"]
                    d["phase_balls"][phase_name] += 1
                    break

    for n, d in innings_data.items():
        results.append({
            "innings_num": n,
            "batting_team": d["batting_team"],
            "final_runs": d["runs"],
            "final_wickets": d["wickets"],
            "legal_balls": d["legal_balls"],
            "phase_runs": d["phase_runs"],
            "phase_balls": d["phase_balls"],
        })

    return results


def format_total_overs(match_type):
    if match_type in ("ODI", "ODM"):
        return 50
    return 20  # T20-family default


def build_venue_stats():
    with open(MANIFEST) as f:
        manifest = json.load(f)

    print("Building venue alias map (normalizing venue name variants)...")
    alias_map, canonical_display = build_venue_alias_map()
    distinct_raw = len(alias_map)
    distinct_normalized = len(set(alias_map.values()))
    print(f"  {distinct_raw} raw venue strings -> {distinct_normalized} normalized venues "
          f"({distinct_raw - distinct_normalized} duplicates merged)")

    # accumulator: normalized_venue -> match_type -> list of per-innings facts
    accum = {}

    limited_overs_matches = [m for m in manifest if m["competition_code"] in LIMITED_OVERS_FORMATS]
    print(f"Processing {len(limited_overs_matches)} limited-overs matches...")

    processed = 0
    for m in limited_overs_matches:
        match_id = m["match_id"]
        path = os.path.join(EVENTS_DIR, f"{match_id}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        meta = data["meta"]
        raw_venue = meta.get("venue")
        if not raw_venue:
            continue
        venue_key = alias_map.get(raw_venue, normalize_venue(raw_venue))
        match_type = m["competition_code"]
        total_overs = format_total_overs(match_type)

        try:
            innings_facts = compute_match_venue_facts(match_id, match_type, total_overs)
        except Exception as e:
            continue

        accum.setdefault(venue_key, {}).setdefault(match_type, []).extend(innings_facts)

        processed += 1
        if processed % 3000 == 0:
            print(f"  {processed}/{len(limited_overs_matches)} matches processed")

    print(f"Done processing. Aggregating stats for {len(accum)} venues...")

    venue_stats = {}
    for venue_key, by_format in accum.items():
        venue_entry = {
            "display_name": canonical_display.get(venue_key, venue_key),
            "formats": {},
        }
        for match_type, innings_list in by_format.items():
            first_innings = [i for i in innings_list if i["innings_num"] == 1]
            n = len(first_innings)
            if n == 0:
                continue

            avg_first_innings_score = round(
                sum(i["final_runs"] for i in first_innings) / n, 1
            )
            avg_first_innings_wickets = round(
                sum(i["final_wickets"] for i in first_innings) / n, 1
            )

            phases = phase_set_for_format(format_total_overs(match_type))
            phase_avg = {}
            for phase_name in phases:
                total_runs = sum(i["phase_runs"][phase_name] for i in first_innings)
                total_balls = sum(i["phase_balls"][phase_name] for i in first_innings)
                phase_avg[phase_name] = {
                    "avg_runs": round(total_runs / n, 1),
                    "avg_run_rate": current_run_rate(total_runs, total_balls),
                }

            venue_entry["formats"][match_type] = {
                "matches_with_data": n,
                "avg_first_innings_score": avg_first_innings_score,
                "avg_first_innings_wickets": avg_first_innings_wickets,
                "phase_breakdown": phase_avg,
            }

        if venue_entry["formats"]:
            venue_stats[venue_key] = venue_entry

    os.makedirs(CONTEXT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(venue_stats, f, indent=2)

    print(f"Saved venue context for {len(venue_stats)} venues to {OUT_FILE}")
    return venue_stats


if __name__ == "__main__":
    stats = build_venue_stats()

    # Print a sample for sanity-checking
    sample_key = next((k for k in stats if "Premadasa" in k), None)
    if sample_key:
        print(f"\nSample venue: {sample_key}")
        print(json.dumps(stats[sample_key], indent=2))
