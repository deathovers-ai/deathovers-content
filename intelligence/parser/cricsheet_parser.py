"""
Epic 1 - Task: Parser that converts CricSheet JSON into DeathOvers internal
ball event schema. See schema/event_schema.md for the target format.

This is the ONLY place in the codebase allowed to read raw Cricsheet JSON.
Everything else (Replay Engine, Metrics, Context Repository) consumes the
flat event list this produces.
"""
import json
import os

EXTRA_KEYS = ["wides", "noballs", "byes", "legbyes", "penalty"]


def parse_actual_delivery(s):
    """'0.4' -> (over=0, ball_in_over=4)"""
    over_str, ball_str = s.split(".")
    return int(over_str), int(ball_str)


def parse_match(filepath):
    """
    Parse a single Cricsheet match JSON file into a dict:
    {
      "match_id": str,
      "meta": {...},           # date, venue, teams, competition, outcome
      "events": [ball_event, ...]   # flat, ordered list across all innings
    }
    """
    with open(filepath, encoding="utf-8") as f:
        raw = json.load(f)

    info = raw["info"]
    match_id = os.path.splitext(os.path.basename(filepath))[0]

    meta = {
        "match_id": match_id,
        "dates": info.get("dates", []),
        "match_type": info.get("match_type"),
        "gender": info.get("gender"),
        "venue": info.get("venue"),
        "city": info.get("city"),
        "event_name": info.get("event", {}).get("name"),
        "season": info.get("season"),
        "teams": info.get("teams", []),
        "toss": info.get("toss", {}),
        "outcome": info.get("outcome", {}),
        "player_of_match": info.get("player_of_match", []),
        "balls_per_over": info.get("balls_per_over", 6),
    }

    events = []
    for innings_num, innings in enumerate(raw["innings"], start=1):
        batting_team = innings["team"]
        bowling_team = next((t for t in meta["teams"] if t != batting_team), None)

        # Forfeited innings (declaration games, some abandoned matches) have
        # no "overs" key at all - no deliveries were bowled. Skip cleanly
        # rather than crash; record it so the replay engine knows this
        # innings never happened.
        if innings.get("forfeited"):
            continue

        delivery_seq = 0
        for over_block in innings.get("overs", []):
            for delivery in over_block["deliveries"]:
                delivery_seq += 1
                over, ball_in_over = parse_actual_delivery(delivery["actual_delivery"])

                runs = delivery.get("runs", {})
                runs_batter = runs.get("batter", 0)
                runs_extras = runs.get("extras", 0)
                runs_total = runs.get("total", runs_batter + runs_extras)

                extras_detail = delivery.get("extras", {}) or {}
                extra_type = next((k for k in EXTRA_KEYS if k in extras_detail), None)
                is_legal = not extras_detail.get("wides") and not extras_detail.get("noballs")

                wickets_raw = delivery.get("wickets", []) or []
                wickets = [
                    {
                        "kind": w.get("kind"),
                        "player_out": w.get("player_out"),
                        "fielders": [fl.get("name") for fl in w.get("fielders", []) if fl.get("name")],
                    }
                    for w in wickets_raw
                ]

                event = {
                    "match_id": match_id,
                    "innings_num": innings_num,
                    "batting_team": batting_team,
                    "bowling_team": bowling_team,
                    "over": over,
                    "ball_in_over": ball_in_over,
                    "delivery_seq": delivery_seq,
                    "batter": delivery.get("batter"),
                    "non_striker": delivery.get("non_striker"),
                    "bowler": delivery.get("bowler"),
                    "runs_batter": runs_batter,
                    "runs_extras": runs_extras,
                    "runs_total": runs_total,
                    "extra_type": extra_type,
                    "extras_detail": extras_detail,
                    "is_legal_delivery": is_legal,
                    "is_wicket": len(wickets) > 0,
                    "wickets": wickets,
                    "match_type": meta["match_type"],
                    "gender": meta["gender"],
                    "season": meta["season"],
                    "venue": meta["venue"],
                    "city": meta["city"],
                }
                events.append(event)

    return {"match_id": match_id, "meta": meta, "events": events}


if __name__ == "__main__":
    # quick self-test on the sample match
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parsed = parse_match(os.path.join(_base, "raw_data", "1000851.json"))
    print("Match:", parsed["match_id"], parsed["meta"]["teams"], parsed["meta"]["match_type"])
    print("Total balls parsed:", len(parsed["events"]))
    print("First ball:", json.dumps(parsed["events"][0], indent=2))
    print("Wicket ball sample:")
    for e in parsed["events"]:
        if e["is_wicket"]:
            print(json.dumps(e, indent=2))
            break
