"""
Epic 3 - Core Metrics Engine

Goal: Produce reliable FACTS, not insights. These are internal building
blocks - the Insight Engine (a later layer) is what interprets them.
This layer never judges, labels, or flags anything as "good/bad/on-track" -
it only counts and calculates.

Computes exactly:
  - Runs
  - Wickets
  - Overs
  - Balls
  - Extras
  - Fours
  - Sixes
  - Dot balls
  - Singles
  - Doubles
  - Triples
  - Strike rate
  - Economy rate
  - Current run rate
  - Required run rate (second innings only)

Consumes a MatchState object from replay_engine.py. Does not read raw
data directly.
"""


def strike_rate(runs, balls):
    """Batter strike rate: runs per 100 balls faced."""
    if balls == 0:
        return 0.0
    return round((runs / balls) * 100, 2)


def economy_rate(runs_conceded, balls_bowled):
    """Bowler economy: runs conceded per 6-ball over."""
    if balls_bowled == 0:
        return 0.0
    overs = balls_bowled / 6
    return round(runs_conceded / overs, 2)


def current_run_rate(runs, legal_balls_bowled):
    """Runs per over, for the batting team, at the current point."""
    if legal_balls_bowled == 0:
        return 0.0
    overs = legal_balls_bowled / 6
    return round(runs / overs, 2)


def required_run_rate(runs_needed, balls_remaining):
    """
    RRR for a chasing (2nd innings) team only.
    runs_needed: target - current score (can be <= 0 if already won)
    balls_remaining: legal balls left in the innings
    Returns None if not applicable (no balls left).
    """
    if balls_remaining <= 0:
        return None
    overs_remaining = balls_remaining / 6
    return round(runs_needed / overs_remaining, 2)


def balls_to_overs_str(legal_balls):
    """60 legal balls -> '10.0', 63 -> '10.3'"""
    overs = legal_balls // 6
    balls = legal_balls % 6
    return f"{overs}.{balls}"


def count_run_type(recent_balls, run_value):
    """Count legal deliveries where exactly `run_value` runs were scored
    off the bat/total (used for singles=1, doubles=2, triples=3, dots=0)."""
    return sum(1 for b in recent_balls if b["runs_total"] == run_value)


class MetricsEngine:
    """
    Computes the exact, fixed set of facts above from a MatchState
    (see replay_engine.py), at whatever point that state has been
    advanced to.

    Usage:
        engine = ReplayEngine(match_id)
        engine.replay_to(1, 9, 6)          # fast-forward to end of over 10
        state = engine._innings_states[1]
        facts = MetricsEngine(state, target=None, total_overs=20).compute()
    """

    def __init__(self, match_state, target=None, total_overs=20):
        """
        match_state: MatchState object, already advanced to the desired point.
        target:      runs required to win. Only meaningful for the 2nd
                      innings of a chase. None otherwise - required_run_rate
                      will then be omitted.
        total_overs: format's max legal overs (20 for T20, 50 for ODI).
        """
        self.s = match_state
        self.target = target
        self.total_overs = total_overs

    def team_facts(self):
        s = self.s
        total_legal_balls = self.total_overs * 6
        balls_remaining = max(total_legal_balls - s.legal_balls, 0)

        facts = {
            "runs": s.runs,
            "wickets": s.wickets,
            "overs": balls_to_overs_str(s.legal_balls),
            "balls": s.legal_balls,
            "extras": s.extras_total,
            "fours": s.fours,
            "sixes": s.sixes,
            "dot_balls": count_run_type(s.recent_balls, 0),
            "singles": count_run_type(s.recent_balls, 1),
            "doubles": count_run_type(s.recent_balls, 2),
            "triples": count_run_type(s.recent_balls, 3),
            "current_run_rate": current_run_rate(s.runs, s.legal_balls),
        }

        if self.target is not None:
            runs_needed = self.target - s.runs
            facts["required_run_rate"] = required_run_rate(runs_needed, balls_remaining)

        return facts

    def batting_facts(self):
        """Per-batter facts, keyed by name."""
        out = {}
        for name, line in self.s.batting_lines.items():
            out[name] = {
                "runs": line["runs"],
                "balls": line["balls"],
                "fours": line["fours"],
                "sixes": line["sixes"],
                "out": line["out"],
                "strike_rate": strike_rate(line["runs"], line["balls"]),
            }
        return out

    def bowling_facts(self):
        """Per-bowler facts, keyed by name."""
        out = {}
        for name, line in self.s.bowling_lines.items():
            out[name] = {
                "runs": line["runs"],
                "balls": line["balls"],
                "overs": balls_to_overs_str(line["balls"]),
                "wickets": line["wickets"],
                "economy": economy_rate(line["runs"], line["balls"]),
            }
        return out

    def compute(self):
        return {
            "team": self.team_facts(),
            "batting": self.batting_facts(),
            "bowling": self.bowling_facts(),
        }


if __name__ == "__main__":
    import json
    import os
    from replay_engine import ReplayEngine

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base_dir, "output", "manifest.json")) as f:
        manifest = json.load(f)
    ipl_match = next(m for m in manifest if m["competition_code"] == "IPL")
    match_id = ipl_match["match_id"]
    print(f"Metrics test on IPL match {match_id}: {ipl_match['teams']}")

    # Innings 1, no target
    engine = ReplayEngine(match_id)
    engine.replay_to(1, 9, 6)  # end of over 10
    state1 = engine._innings_states[1]
    facts1 = MetricsEngine(state1, target=None, total_overs=20).compute()
    print("\n--- Innings 1 facts after 10 overs ---")
    print(json.dumps(facts1["team"], indent=2))

    # Innings 2, with target from innings 1 final score
    final1 = engine.final_state(1)
    target = final1["score"] + 1

    engine2 = ReplayEngine(match_id)
    engine2.replay_to(2, 9, 6)
    state2 = engine2._innings_states[2]
    facts2 = MetricsEngine(state2, target=target, total_overs=20).compute()
    print(f"\n--- Innings 2 (target {target}) facts after 10 overs ---")
    print(json.dumps(facts2["team"], indent=2))

    # Sanity check: dot+singles+doubles+triples+fours+sixes should roughly
    # match legal balls bowled (minus any 5s, which are rare but real)
    t = facts2["team"]
    accounted = t["dot_balls"] + t["singles"] + t["doubles"] + t["triples"] + t["fours"] + t["sixes"]
    print(f"\nSanity check: legal balls={t['balls']}, accounted for by run-type counts={accounted} "
          f"(difference = balls scored as 5s, if any)")
