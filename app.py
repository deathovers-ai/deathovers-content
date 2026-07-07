import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enables cross-origin requests for your Vercel frontend

# Securely load your API keys from environment variables
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "YOUR_FALLBACK_KEY_IF_NOT_SET")
RAPIDAPI_HOST = "cricket-live-score-data.p.rapidapi.com"

# --- CORE MATH UTILITIES: IMPACT METRICS ---
def calculate_batting_impact(runs, balls, phase):
    """
    VORP Logic: Measures runs scored above/below the historical T20 baseline.
    Powerplay Baseline SR: 120.0 | Middle Baseline SR: 130.0 | Death Baseline SR: 158.3
    """
    if balls <= 0:
        return 0.0
    
    if phase.lower() == "powerplay":
        expected_rpo = 7.2  # 120 SR
    elif phase.lower() == "death":
        expected_rpo = 9.5  # 158.3 SR
    else:
        expected_rpo = 7.8  # 130 SR

    expected_runs = (balls / 6.0) * expected_rpo
    net_runs_above_baseline = runs - expected_runs
    return round(net_runs_above_baseline, 2)


def calculate_bowling_impact(overs, runs_conceded, wickets, phase):
    """
    VORP Logic: Measures runs saved below historical phase expectations + wicket premiums.
    """
    if overs <= 0:
        return 0.0
    
    if phase.lower() == "powerplay":
        expected_eco = 7.2
    elif phase.lower() == "death":
        expected_eco = 9.5
    else:
        expected_eco = 7.8

    expected_runs = overs * expected_eco
    runs_saved = expected_runs - runs_conceded
    wicket_premium = wickets * 15.0  # Assigns a 15-run value premium per wicket
    
    return round(runs_saved + wicket_premium, 2)


# --- API ROUTE 1: THE LIVE/UPCOMING SUMMARY CAROUSEL ---
@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    """
    Pings RapidAPI to get active live matches and upcoming fixtures.
    Returns clean arrays matching your LiveCarousel.jsx component expectations.
    """
    url = f"https://{RAPIDAPI_HOST}/matches-live"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        # Real-time fetch layer
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            raw_data = response.json()
            
            # Map the response into the exact data objects expected by your frontend carousel
            live_and_recent = []
            upcoming = []
            
            for match in raw_data.get("results", []):
                match_obj = {
                    "id": str(match.get("match_id")),
                    "matchName": f"{match.get('home_team')} vs {match.get('away_team')}",
                    "venue": match.get("venue", "TBD International Ground"),
                    "status": "LIVE" if match.get("live") else "CONCLUDED",
                    "chaseNote": match.get("status_note", ""),
                    "score": {
                        "home": {
                            "score": match.get("home_score", "-"),
                            "info": match.get("home_overs", "")
                        },
                        "away": {
                            "score": match.get("away_score", "-"),
                            "info": match.get("away_overs", "")
                        }
                    }
                }
                
                if match.get("live"):
                    live_and_recent.append(match_obj)
                else:
                    upcoming.append(match_obj)
                    
            # Fallback handling: If the cricket calendar has zero scheduled matches today,
            # return empty arrays so our frontend can seamlessly render the simulated mock view.
            return jsonify({
                "liveAndRecent": live_and_recent,
                "upcoming": upcoming
            })
            
        return jsonify({"liveAndRecent": [], "upcoming": []}), response.status_code
        
    except Exception as e:
        print(f"Telemetry API error intercepted: {str(e)}")
        return jsonify({"liveAndRecent": [], "upcoming": [], "error": "API offline"}), 500


# --- API ROUTE 2: THE DEEP DRILLDOWN & PERFORMANCE INDEX ---
@app.route('/api/match-details/<match_id>', methods=['GET'])
def get_match_details(match_id):
    """
    Fetches full dynamic ball-by-ball actions for a specific match,
    runs the performance index engine, and yields multi-innings dashboards.
    """
    url = f"https://{RAPIDAPI_HOST}/match-scorecard"
    querystring = {"match_id": match_id}
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        
        # --- SCENARIO A: PRODUCTION RUN (API LIVE AND RESPONDING) ---
        if response.status_code == 200:
            raw_card = response.json().get("results", {})
            
            # Dynamically compile Innings 1 and Innings 2 from scorecard parameters
            # Map values out cleanly to match the structure expected by the front end
            payload = {
                "innings1": {
                    "teamName": raw_card.get("innings_1_team", "GT"),
                    "batsmen": [{"name": b.get("name"), "runs": int(b.get("runs")), "balls": int(b.get("balls")), "fours": int(b.get("fours")), "sixes": int(b.get("sixes")), "sr": float(b.get("strike_rate"))} for b in raw_card.get("innings_1_batting", [])],
                    "bowlers": [{"name": b.get("name"), "overs": b.get("overs"), "maidens": int(b.get("maidens")), "runs": int(b.get("runs")), "wickets": int(b.get("wickets")), "econ": float(b.get("economy")), "currentSpell": "Spell Concluded"} for b in raw_card.get("innings_1_bowling", [])]
                },
                "innings2": {
                    "teamName": raw_card.get("innings_2_team", "KKR"),
                    "batsmen": [{"name": b.get("name"), "runs": int(b.get("runs")), "balls": int(b.get("balls")), "fours": int(b.get("fours")), "sixes": int(b.get("sixes")), "sr": float(b.get("strike_rate"))} for b in raw_card.get("innings_2_batting", [])],
                    "bowlers": [{"name": b.get("name"), "overs": b.get("overs"), "maidens": int(b.get("maidens")), "runs": int(b.get("runs")), "wickets": int(b.get("wickets")), "econ": float(b.get("economy")), "currentSpell": "Active"} for b in raw_card.get("innings_2_bowling", [])]
                },
                "commentary": [{"over": c.get("over"), "event": c.get("event"), "desc": c.get("description")} for c in raw_card.get("live_commentary", [])[:10]]
            }
            return
