# DeathOvers Internal Ball Event Schema (v1)

One record per delivery. This is the single source of truth format that
the Replay Engine, Metrics Engine, and Context Repository all consume.
Nothing downstream ever reads raw Cricsheet JSON directly.

Example event:

    {
      "match_id": "1000851",
      "innings_num": 1,
      "batting_team": "South Africa",
      "bowling_team": "Australia",
      "over": 0,
      "ball_in_over": 1,
      "delivery_seq": 1,
      "batter": "SC Cook",
      "non_striker": "D Elgar",
      "bowler": "MA Starc",
      "runs_batter": 0,
      "runs_extras": 0,
      "runs_total": 0,
      "extra_type": null,
      "is_legal_delivery": true,
      "is_wicket": false,
      "wickets": []
    }

## Field notes

- delivery_seq: running count of ALL deliveries in the innings (legal + illegal), 1-indexed. Used as the replay engine's tick counter.
- over / ball_in_over: taken directly from Cricsheet's actual_delivery (e.g. "0.4" -> over=0, ball_in_over=4). NOT recalculated, because wides/no-balls don't advance ball_in_over in Cricsheet's own numbering - we trust their numbering as ground truth.
- extra_type: one of wides, noballs, byes, legbyes, penalty, or null.
- is_legal_delivery: false if wides or noballs present (these don't count toward the 6-ball over).
- is_wicket: true if a wickets list is present and non-empty.
- wickets: list of {kind, player_out, fielders: [names]}. Almost always length 1.

## Extended fields (denormalized onto every ball row)

    {
      "extras_detail": {"wides": 1},
      "match_type": "IPL",
      "gender": "male",
      "season": "2016",
      "venue": "WACA Ground",
      "city": "Perth"
    }

Match-level fields (match_type, gender, season, venue, city) are
denormalized onto every ball row deliberately - this is a flat event log,
not a normalized relational table. Optimized for the Replay Engine to
scan sequentially without joins. The Context Repository will later
aggregate this into venue/team/player tables.
