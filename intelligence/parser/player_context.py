"""
Epic 4b / F04 - Player context (career + form / venue / phase).

Career aggregates stay as before. Enrichment adds:
  - form: last_10_innings, last_5_innings, last_2y batting windows
  - venues: per-venue batting/bowling (gated at read-time by MIN_VENUE_INNINGS)
  - phases: per-format powerplay/middle/death batting (gated by MIN_PHASE_BALLS)

IMPORTANT: player identity merges only via player_aliases.json (registry-
confirmed). Never guess merges from name patterns.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import determine_phase_from_over
from context_freshness import write_context_meta, infer_corpus_through_from_players
from context_repository import normalize_venue
from validation_engine import MIN_PHASE_BALLS, MIN_VENUE_INNINGS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_DIR = os.path.join(BASE_DIR, "output", "events")
MANIFEST = os.path.join(BASE_DIR, "output", "manifest.json")
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
PLAYER_STATS_FILE = os.path.join(CONTEXT_DIR, "player_stats.json")
ALIASES_FILE = os.path.join(CONTEXT_DIR, "player_aliases.json")

LIMITED_OVERS_FORMATS = {"T20", "IT20", "IPL", "ODI", "ODM"}


def load_aliases():
    if os.path.exists(ALIASES_FILE):
        with open(ALIASES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def canonical_name(raw_name, aliases):
    return aliases.get(raw_name, raw_name)


def _empty_bat():
    return {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "dismissals": 0, "innings": 0}


def _empty_bowl():
    return {"runs": 0, "balls": 0, "wickets": 0, "innings": 0}


def _finalize_bat(bat: dict) -> dict:
    balls = bat["balls"]
    dismissals = bat["dismissals"]
    return {
        **bat,
        "strike_rate": round((bat["runs"] / balls) * 100, 2) if balls else 0.0,
        "average": round(bat["runs"] / dismissals, 2) if dismissals else None,
    }


def _finalize_bowl(bowl: dict) -> dict:
    balls = bowl["balls"]
    wickets = bowl["wickets"]
    return {
        **bowl,
        "economy": round(bowl["runs"] / (balls / 6), 2) if balls else 0.0,
        "average": round(bowl["runs"] / wickets, 2) if wickets else None,
    }


def _window_from_innings(innings_rows: list[dict], limit: int | None = None) -> dict:
    rows = innings_rows[-limit:] if limit else list(innings_rows)
    bat = _empty_bat()
    for row in rows:
        bat["runs"] += row["runs"]
        bat["balls"] += row["balls"]
        bat["fours"] += row["fours"]
        bat["sixes"] += row["sixes"]
        bat["dismissals"] += row["dismissals"]
        bat["innings"] += 1
    return _finalize_bat(bat)


def competition_code_for_match(meta: dict, manifest_code: str | None = None) -> str | None:
    if manifest_code in LIMITED_OVERS_FORMATS:
        return manifest_code
    event_name = (meta.get("event_name") or "").lower()
    if "indian premier league" in event_name or event_name == "ipl":
        return "IPL"
    match_type = (meta.get("match_type") or "").upper()
    if match_type in LIMITED_OVERS_FORMATS:
        return match_type
    return None


def _touch_dates(entry: dict, match_date: str | None) -> None:
    if not match_date:
        return
    if entry["earliest_match_date"] is None or match_date < entry["earliest_match_date"]:
        entry["earliest_match_date"] = match_date
    if entry["latest_match_date"] is None or match_date > entry["latest_match_date"]:
        entry["latest_match_date"] = match_date


def _venue_bucket(players: dict, name: str, venue_key: str) -> dict:
    return players[name]["_venues"].setdefault(venue_key, {
        "batting": _empty_bat(),
        "bowling": _empty_bowl(),
        "_bat_keys": set(),
        "_bowl_keys": set(),
    })


def build_player_stats(events_dir: str = EVENTS_DIR, manifest_path: str = MANIFEST,
                       out_path: str = PLAYER_STATS_FILE, merge_existing: bool = False):
    """
    Build player stats from parsed events.

    If merge_existing=True and out_path already has career stats, keep those
    career batting/bowling blocks and only refresh form/venues/phases from
    the events currently on disk.
    """
    manifest_by_id = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            for m in json.load(f):
                manifest_by_id[str(m["match_id"])] = m

    aliases = load_aliases()
    print(
        f"Loaded {len(aliases)} confirmed name aliases - applying during aggregation."
        if aliases else
        "No player_aliases.json found - proceeding with raw names as-is."
    )

    existing = {}
    if merge_existing and os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"Merging enrichment into existing {len(existing)} player entries.")

    players = defaultdict(lambda: {
        "batting": _empty_bat(),
        "bowling": _empty_bowl(),
        "earliest_match_date": None,
        "latest_match_date": None,
        "_bat_innings": [],
        "_venues": {},
        "_phases": {},
        "_bat_innings_seen": set(),
        "_bowl_innings_seen": set(),
    })

    event_files = []
    if os.path.isdir(events_dir):
        if manifest_by_id:
            for match_id, m in manifest_by_id.items():
                path = os.path.join(events_dir, f"{match_id}.json")
                if os.path.exists(path):
                    event_files.append((path, m.get("competition_code")))
        else:
            for name in sorted(os.listdir(events_dir)):
                if name.endswith(".json"):
                    event_files.append((os.path.join(events_dir, name), None))

    print(f"Processing {len(event_files)} event files for player stats...")

    processed = 0
    for path, manifest_code in event_files:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        meta = data["meta"]
        match_id = str(meta.get("match_id") or os.path.splitext(os.path.basename(path))[0])
        match_dates = meta.get("dates") or []
        match_date = match_dates[0] if match_dates else None
        venue_key = normalize_venue(meta["venue"]) if meta.get("venue") else None
        match_format = competition_code_for_match(meta, manifest_code)
        if match_format is None:
            continue

        innings_bat = defaultdict(lambda: {
            "runs": 0, "balls": 0, "fours": 0, "sixes": 0, "dismissals": 0,
        })

        for event in data["events"]:
            batter = canonical_name(event["batter"], aliases)
            bowler = canonical_name(event["bowler"], aliases)
            phase = determine_phase_from_over(event["over"], match_format)
            innings_key = f"{match_id}:{event['innings_num']}"

            _touch_dates(players[batter], match_date)
            _touch_dates(players[bowler], match_date)

            # --- batting ---
            if event["extra_type"] != "wides":
                bat = players[batter]["batting"]
                bat["balls"] += 1
                bat["runs"] += event["runs_batter"]
                if event["runs_batter"] == 4:
                    bat["fours"] += 1
                if event["runs_batter"] == 6:
                    bat["sixes"] += 1

                line = innings_bat[batter]
                line["balls"] += 1
                line["runs"] += event["runs_batter"]
                if event["runs_batter"] == 4:
                    line["fours"] += 1
                if event["runs_batter"] == 6:
                    line["sixes"] += 1

                phase_bucket = None
                if phase:
                    phase_bucket = players[batter]["_phases"].setdefault(match_format, {}).setdefault(
                        phase, {"runs": 0, "balls": 0}
                    )
                    phase_bucket["balls"] += 1
                    phase_bucket["runs"] += event["runs_batter"]

                bat_seen_key = f"{innings_key}:{batter}"
                if bat_seen_key not in players[batter]["_bat_innings_seen"]:
                    players[batter]["_bat_innings_seen"].add(bat_seen_key)
                    bat["innings"] += 1

                if venue_key:
                    v = _venue_bucket(players, batter, venue_key)
                    v["batting"]["balls"] += 1
                    v["batting"]["runs"] += event["runs_batter"]
                    if event["runs_batter"] == 4:
                        v["batting"]["fours"] += 1
                    if event["runs_batter"] == 6:
                        v["batting"]["sixes"] += 1
                    if innings_key not in v["_bat_keys"]:
                        v["_bat_keys"].add(innings_key)
                        v["batting"]["innings"] += 1

            # --- bowling ---
            bowl = players[bowler]["bowling"]
            if event["extra_type"] not in ("byes", "legbyes"):
                bowl["runs"] += event["runs_total"]
            if venue_key and event["extra_type"] not in ("byes", "legbyes"):
                _venue_bucket(players, bowler, venue_key)["bowling"]["runs"] += event["runs_total"]

            if event["is_legal_delivery"]:
                bowl["balls"] += 1
                bowl_seen_key = f"{innings_key}:{bowler}"
                if bowl_seen_key not in players[bowler]["_bowl_innings_seen"]:
                    players[bowler]["_bowl_innings_seen"].add(bowl_seen_key)
                    bowl["innings"] += 1

                if venue_key:
                    v = _venue_bucket(players, bowler, venue_key)
                    v["bowling"]["balls"] += 1
                    if innings_key not in v["_bowl_keys"]:
                        v["_bowl_keys"].add(innings_key)
                        v["bowling"]["innings"] += 1

            if event["is_wicket"]:
                for w in event["wickets"]:
                    dismissed = canonical_name(w["player_out"], aliases)
                    players[dismissed]["batting"]["dismissals"] += 1
                    innings_bat[dismissed]["dismissals"] += 1
                    if w["kind"] not in ("run out",):
                        bowl["wickets"] += 1
                        if venue_key:
                            _venue_bucket(players, bowler, venue_key)["bowling"]["wickets"] += 1

        for batter, line in innings_bat.items():
            if line["balls"] == 0 and line["dismissals"] == 0:
                continue
            players[batter]["_bat_innings"].append({
                "date": match_date,
                "match_id": match_id,
                "venue": venue_key,
                "format": match_format,
                **line,
            })

        processed += 1
        if processed % 1000 == 0:
            print(f"  {processed}/{len(event_files)} matches processed")

    print("Computing derived rates and enrichment windows...")
    built = {}
    for name, stats in players.items():
        innings_rows = [row for row in stats["_bat_innings"] if row.get("date")]
        innings_rows.sort(key=lambda r: (r["date"], r["match_id"]))

        latest = stats["latest_match_date"]
        last_2y_rows = innings_rows
        if latest:
            try:
                cutoff = (datetime.strptime(latest, "%Y-%m-%d").date() - timedelta(days=730)).isoformat()
                last_2y_rows = [r for r in innings_rows if r["date"] >= cutoff]
            except ValueError:
                pass

        venues_out = {}
        for venue_key, v in stats["_venues"].items():
            bat = _finalize_bat({k: v["batting"][k] for k in _empty_bat()})
            bowl = _finalize_bowl({k: v["bowling"][k] for k in _empty_bowl()})
            # Drop thin venue samples from the committed blob — guards would
            # refuse them at read-time anyway, and they dominate file size.
            if bat["innings"] < MIN_VENUE_INNINGS and bowl["innings"] < MIN_VENUE_INNINGS:
                continue
            venues_out[venue_key] = {"batting": bat, "bowling": bowl}

        phases_out = {}
        for fmt, phases in stats["_phases"].items():
            phases_out[fmt] = {}
            for phase_name, bucket in phases.items():
                balls = bucket["balls"]
                phases_out[fmt][phase_name] = {
                    "runs": bucket["runs"],
                    "balls": balls,
                    "strike_rate": round((bucket["runs"] / balls) * 100, 2) if balls else 0.0,
                    "reliable": balls >= MIN_PHASE_BALLS,
                }

        built[name] = {
            "batting": _finalize_bat(stats["batting"]),
            "bowling": _finalize_bowl(stats["bowling"]),
            "earliest_match_date": stats["earliest_match_date"],
            "latest_match_date": stats["latest_match_date"],
            "form": {
                "last_10_innings": _window_from_innings(innings_rows, 10),
                "last_5_innings": _window_from_innings(innings_rows, 5),
                "last_2y": _window_from_innings(last_2y_rows),
            },
            "venues": venues_out,
            "phases": phases_out,
        }

    if merge_existing and existing:
        output = dict(existing)
        for name, enriched in built.items():
            base = dict(output.get(name) or {})
            if "batting" not in base:
                base["batting"] = enriched["batting"]
            if "bowling" not in base:
                base["bowling"] = enriched["bowling"]
            if not base.get("earliest_match_date"):
                base["earliest_match_date"] = enriched["earliest_match_date"]
            elif enriched["earliest_match_date"] and enriched["earliest_match_date"] < base["earliest_match_date"]:
                base["earliest_match_date"] = enriched["earliest_match_date"]
            if not base.get("latest_match_date"):
                base["latest_match_date"] = enriched["latest_match_date"]
            elif enriched["latest_match_date"] and enriched["latest_match_date"] > base["latest_match_date"]:
                base["latest_match_date"] = enriched["latest_match_date"]
            base["form"] = enriched["form"]
            base["venues"] = enriched["venues"]
            base["phases"] = enriched["phases"]
            output[name] = base
    else:
        output = built

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f)
    corpus_through = infer_corpus_through_from_players(output)
    write_context_meta(corpus_through)
    print(f"Saved player stats for {len(output)} name-entries to {out_path}")
    print(f"Context meta corpus_through={corpus_through}")
    print(f"Enriched from events: {len(built)} players")
    return output


if __name__ == "__main__":
    import argparse
    cli = argparse.ArgumentParser(description="Build player context (+ F04 enrichment).")
    cli.add_argument("--merge-existing", action="store_true",
                     help="Keep existing career stats; refresh form/venues/phases from events.")
    cli.add_argument("--out", default=PLAYER_STATS_FILE)
    args = cli.parse_args()
    stats = build_player_stats(out_path=args.out, merge_existing=args.merge_existing)
    sample = stats.get("V Kohli")
    if sample:
        print("\nSample player: V Kohli")
        slim = {k: sample[k] for k in ("batting", "earliest_match_date", "latest_match_date", "form")}
        slim["phase_formats"] = list((sample.get("phases") or {}).keys())
        slim["venue_count"] = len(sample.get("venues") or {})
        print(json.dumps(slim, indent=2))
