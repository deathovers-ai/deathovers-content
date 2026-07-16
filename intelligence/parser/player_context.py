"""
Epic 4b - Context Repository (Player layer)

IMPORTANT DESIGN NOTE: player identity resolution across name variants
is handled via player_aliases.json (built by registry_verification.py
from Cricsheet's own verified player registry - NOT by guessing from
name string patterns). If player_aliases.json exists, this script
applies those confirmed merges. If it doesn't exist yet, stats are
built on raw names as-is (safe default, no merging).
"""
import json
import os
from collections import defaultdict

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


def build_player_stats():
    with open(MANIFEST) as f:
        manifest = json.load(f)

    aliases = load_aliases()
    if aliases:
        print(f"Loaded {len(aliases)} confirmed name aliases - applying during aggregation.")
    else:
        print("No player_aliases.json found - proceeding with raw names as-is.")

    limited_overs_matches = [m for m in manifest if m["competition_code"] in LIMITED_OVERS_FORMATS]
    print(f"Processing {len(limited_overs_matches)} limited-overs matches for player stats...")

    players = defaultdict(lambda: {
        "batting": {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "dismissals": 0, "innings": 0},
        "bowling": {"runs": 0, "balls": 0, "wickets": 0, "innings": 0},
        "earliest_match_date": None,
        "latest_match_date": None,
    })
    batted_innings_seen = defaultdict(set)
    bowled_innings_seen = defaultdict(set)

    processed = 0
    for m in limited_overs_matches:
        match_id = m["match_id"]
        path = os.path.join(EVENTS_DIR, f"{match_id}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        match_dates = data["meta"].get("dates", [])
        match_date = match_dates[0] if match_dates else None

        for event in data["events"]:
            batter = canonical_name(event["batter"], aliases)
            bowler = canonical_name(event["bowler"], aliases)

            for name in (batter, bowler):
                entry = players[name]
                if match_date:
                    if entry["earliest_match_date"] is None or match_date < entry["earliest_match_date"]:
                        entry["earliest_match_date"] = match_date
                    if entry["latest_match_date"] is None or match_date > entry["latest_match_date"]:
                        entry["latest_match_date"] = match_date

            innings_key = f"{match_id}:{event['innings_num']}"

            bat_stats = players[batter]["batting"]
            if event["extra_type"] != "wides":
                bat_stats["balls"] += 1
                bat_stats["runs"] += event["runs_batter"]
                if event["runs_batter"] == 4:
                    bat_stats["fours"] += 1
                if event["runs_batter"] == 6:
                    bat_stats["sixes"] += 1
            if innings_key not in batted_innings_seen[batter]:
                batted_innings_seen[batter].add(innings_key)
                bat_stats["innings"] += 1

            bowl_stats = players[bowler]["bowling"]
            if event["extra_type"] not in ("byes", "legbyes"):
                bowl_stats["runs"] += event["runs_total"]
            if event["is_legal_delivery"]:
                bowl_stats["balls"] += 1
            if innings_key not in bowled_innings_seen[bowler]:
                bowled_innings_seen[bowler].add(innings_key)
                bowl_stats["innings"] += 1

            if event["is_wicket"]:
                for w in event["wickets"]:
                    dismissed = canonical_name(w["player_out"], aliases)
                    players[dismissed]["batting"]["dismissals"] += 1
                    if w["kind"] not in ("run out",):
                        bowl_stats["wickets"] += 1

        processed += 1
        if processed % 3000 == 0:
            print(f"  {processed}/{len(limited_overs_matches)} matches processed")

    print("Computing derived rates (strike rate, average, economy)...")
    output = {}
    for name, stats in players.items():
        bat = stats["batting"]
        bowl = stats["bowling"]
        bat_sr = round((bat["runs"] / bat["balls"]) * 100, 2) if bat["balls"] else 0.0
        bat_avg = round(bat["runs"] / bat["dismissals"], 2) if bat["dismissals"] else None
        bowl_econ = round(bowl["runs"] / (bowl["balls"] / 6), 2) if bowl["balls"] else 0.0
        bowl_avg = round(bowl["runs"] / bowl["wickets"], 2) if bowl["wickets"] else None

        output[name] = {
            "batting": {**bat, "strike_rate": bat_sr, "average": bat_avg},
            "bowling": {**bowl, "economy": bowl_econ, "average": bowl_avg},
            "earliest_match_date": stats["earliest_match_date"],
            "latest_match_date": stats["latest_match_date"],
        }

    os.makedirs(CONTEXT_DIR, exist_ok=True)
    with open(PLAYER_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Saved player stats for {len(output)} name-entries to {PLAYER_STATS_FILE}")

    return output


if __name__ == "__main__":
    stats = build_player_stats()
    sample = next((k for k in stats if k == "V Kohli"), None)
    if sample:
        print(f"\nSample player: {sample}")
        print(json.dumps(stats[sample], indent=2))
