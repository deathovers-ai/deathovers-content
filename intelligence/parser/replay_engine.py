"""
Epic 2 - Match Replay Engine
Goal: Reconstruct any match exactly as it happened, ball by ball.

Consumes the internal event schema produced by cricsheet_parser.py
(output/events/<match_id>.json). Never touches raw Cricsheet JSON.

Core object: ReplayEngine
  - .step()          advance exactly one delivery, return new state
  - .replay_to(n)     fast-forward to delivery_seq n within an innings
  - .full_replay()    generator yielding state after every ball
  - .state            current MatchState snapshot (dict)

State tracked (per your doc): innings, over, ball, striker, non-striker,
bowler, and score - updated after every single delivery.
"""
import json
import os

# intelligence/parser/replay_engine.py -> intelligence/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_DIR = os.path.join(BASE_DIR, "output", "events")


class MatchState:
    """Mutable live state of one innings as it's being replayed."""

    def __init__(self, innings_num, batting_team, bowling_team):
        self.innings_num = innings_num
        self.batting_team = batting_team
        self.bowling_team = bowling_team

        self.runs = 0
        self.wickets = 0
        self.legal_balls = 0          # legal deliveries bowled this innings
        self.over = 0
        self.ball_in_over = 0

        self.striker = None
        self.non_striker = None
        self.bowler = None

        self.extras_total = 0
        self.fours = 0
        self.sixes = 0

        # per-batter and per-bowler running lines, keyed by name
        self.batting_lines = {}   # name -> {runs, balls, fours, sixes, out}
        self.bowling_lines = {}   # name -> {runs, balls, wickets}

        self.fall_of_wickets = []  # list of {over, ball, score, wickets, player_out}
        self.recent_balls = []     # last N legal-ball run totals, for trend calc

    def _bat_line(self, name):
        return self.batting_lines.setdefault(
            name, {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "out": False}
        )

    def _bowl_line(self, name):
        return self.bowling_lines.setdefault(
            name, {"runs": 0, "balls": 0, "wickets": 0}
        )

    def apply(self, event):
        """Apply one delivery event, mutating state in place."""
        self.striker = event["batter"]
        self.non_striker = event["non_striker"]
        self.bowler = event["bowler"]

        self.runs += event["runs_total"]
        self.extras_total += event["runs_extras"]

        bat_line = self._bat_line(event["batter"])
        bowl_line = self._bowl_line(event["bowler"])

        # Batter only credited runs off the bat, and only faces a ball on
        # legal deliveries (or no-balls, which do count as a ball faced).
        if event["extra_type"] != "wides":
            bat_line["balls"] += 1
            bat_line["runs"] += event["runs_batter"]
            if event["runs_batter"] == 4:
                bat_line["fours"] += 1
                self.fours += 1
            if event["runs_batter"] == 6:
                bat_line["sixes"] += 1
                self.sixes += 1

        # Bowler concedes all runs except byes/legbyes; balls bowled only
        # count on legal deliveries.
        if event["extra_type"] not in ("byes", "legbyes"):
            bowl_line["runs"] += event["runs_total"]
        if event["is_legal_delivery"]:
            bowl_line["balls"] += 1
            self.legal_balls += 1
            self.over = self.legal_balls // 6
            self.ball_in_over = self.legal_balls % 6

        if event["is_wicket"]:
            self.wickets += len(event["wickets"])
            for w in event["wickets"]:
                if w["player_out"] in self.batting_lines:
                    self.batting_lines[w["player_out"]]["out"] = True
                else:
                    self._bat_line(w["player_out"])["out"] = True
                if w["kind"] not in ("run out",):
                    bowl_line["wickets"] += 1
                self.fall_of_wickets.append({
                    "over": event["over"],
                    "ball": event["ball_in_over"],
                    "score": self.runs,
                    "wickets": self.wickets,
                    "player_out": w["player_out"],
                    "kind": w["kind"],
                })

        if event["is_legal_delivery"]:
            self.recent_balls.append({
                "over": event["over"],
                "ball_in_over": event["ball_in_over"],
                "runs_total": event["runs_total"],
                "is_wicket": event["is_wicket"],
            })

    def snapshot(self):
        return {
            "innings_num": self.innings_num,
            "batting_team": self.batting_team,
            "bowling_team": self.bowling_team,
            "score": self.runs,
            "wickets": self.wickets,
            "overs": f"{self.over}.{self.ball_in_over}",
            "legal_balls_bowled": self.legal_balls,
            "striker": self.striker,
            "non_striker": self.non_striker,
            "bowler": self.bowler,
            "extras": self.extras_total,
            "fours": self.fours,
            "sixes": self.sixes,
        }


class ReplayEngine:
    """
    Deterministically replays one match, ball by ball, across all innings.
    """

    def __init__(self, match_id, events_dir=EVENTS_DIR):
        path = os.path.join(events_dir, f"{match_id}.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self.match_id = match_id
        self.meta = data["meta"]
        self.all_events = data["events"]

        self._innings_states = {}   # innings_num -> MatchState
        self._cursor = 0            # index into self.all_events

    def _get_or_create_state(self, event):
        n = event["innings_num"]
        if n not in self._innings_states:
            self._innings_states[n] = MatchState(
                n, event["batting_team"], event["bowling_team"]
            )
        return self._innings_states[n]

    def step(self):
        """Apply exactly one more delivery. Returns the updated snapshot,
        or None if the match is fully replayed."""
        if self._cursor >= len(self.all_events):
            return None
        event = self.all_events[self._cursor]
        state = self._get_or_create_state(event)
        state.apply(event)
        self._cursor += 1
        return state.snapshot()

    def full_replay(self):
        """Generator: yields (event, snapshot) after every delivery in order."""
        for event in self.all_events:
            state = self._get_or_create_state(event)
            state.apply(event)
            yield event, state.snapshot()

    def replay_to(self, innings_num, over, ball_in_over):
        """Fast-forward and return the state snapshot as of a specific
        over.ball within a specific innings (inclusive). over/ball_in_over
        use Cricsheet's own numbering: over is 0-indexed, ball_in_over is
        1-indexed (1..6, higher for extras). e.g. replay_to(1, 9, 6) stops
        at the end of the 10th over."""
        self._innings_states = {}
        self._cursor = 0
        target_state = None
        for event, snap in self.full_replay():
            if event["innings_num"] == innings_num:
                target_state = snap
                if (event["over"], event["ball_in_over"]) >= (over, ball_in_over):
                    break
            elif event["innings_num"] > innings_num:
                break
        return target_state

    def final_state(self, innings_num=None):
        """Replay the whole match and return final snapshot(s)."""
        self._innings_states = {}
        self._cursor = 0
        for _ in self.full_replay():
            pass
        if innings_num is not None:
            return self._innings_states[innings_num].snapshot()
        return {n: s.snapshot() for n, s in self._innings_states.items()}


if __name__ == "__main__":
    # Self-test: replay a known IPL match end to end and sanity-check score
    with open(os.path.join(BASE_DIR, "output", "manifest.json")) as f:
        manifest = json.load(f)
    ipl_match = next(m for m in manifest if m["competition_code"] == "IPL")
    match_id = ipl_match["match_id"]
    print(f"Replaying IPL match {match_id}: {ipl_match['teams']} ({ipl_match['date']})")

    engine =
