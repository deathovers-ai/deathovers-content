import os
import datetime
from datetime import timezone
import time
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Global Cache Shield
cache = {
    "data": None,
    "timestamp": 0
}
CACHE_DURATION = 30  # 30-second cache threshold

# COO Operational Configurations
COO_HOLD_TIME_MINUTES = 60  # Retain finished matches on screen for 1 hour

def parse_time(time_str):
    if not time_str:
        return 0
    try:
        # Standard API ISO string conversion
        dt = datetime.datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0

@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    current_time = time.time()
    
    # 1. Serve from Cache Shield if fresh
    if cache["data"] and (current_time - cache["timestamp"] < CACHE_DURATION):
        return jsonify(cache["data"])

    rapid_key = os.getenv("RAPIDAPI_KEY")
    today_date = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    url = f"https://cricket-highlights-api.p.rapidapi.com/matches?date={today_date}"
    headers = {
        "x-rapidapi-key": rapid_key,
        "x-rapidapi-host": "cricket-highlights-api.p.rapidapi.com"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            all_matches = res.json().get("data", [])
            
            live_and_recent = []
            upcoming = []
            
            for m in all_matches:
                state_desc = m.get("state", {}).get("description", "")
                
                # Condition A: Match is actively playing
                if state_desc == "In play":
                    live_and_recent.append({
                        "id": m.get("id"),
                        "matchName": f"{m.get('homeTeam', {}).get('name')} vs {m.get('awayTeam', {}).get('name')}",
                        "score": m.get("state", {}).get("teams", {}),
                        "status": "LIVE",
                        "venue": m.get("venue", {}).get("name", "TBD")
                    })
                
                # Condition B: Match concluded, check against COO time buffer
                elif state_desc == "Complete":
                    end_time_stamp = parse_time(m.get("endTime"))
                    time_elapsed_seconds = current_time - end_time_stamp
                    
                    if time_elapsed_seconds < (COO_HOLD_TIME_MINUTES * 60):
                        live_and_recent.append({
                            "id": m.get("id"),
                            "matchName": f"{m.get('homeTeam', {}).get('name')} vs {m.get('awayTeam', {}).get('name')}",
                            "score": m.get("state", {}).get("teams", {}),
                            "status": "CONCLUDED",
                            "venue": m.get("venue", {}).get("name", "TBD")
                        })
                
                # Condition C: Match is scheduled for later
                else:
                    upcoming.append({
                        "id": m.get("id"),
                        "matchName": f"{m.get('homeTeam', {}).get('name')} vs {m.get('awayTeam', {}).get('name')}",
                        "startTime": m.get("startTime"),
                        "venue": m.get("venue", {}).get("name", "TBD")
                    })

            response_payload = {
                "liveAndRecent": live_and_recent,
                "upcoming": upcoming[:3]  # Keep top 3 upcoming fixtures
            }
            
            # Save to cache shield
            cache["data"] = response_payload
            cache["timestamp"] = current_time
            return jsonify(response_payload)
            
    except Exception as e:
        if cache["data"]:
            return jsonify(cache["data"])
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"liveAndRecent": [], "upcoming": []})

# --- ONS-DEMAND LAZY LOAD CHANNELS FOR PARTICULARS ---
@app.route('/api/match-details/<match_id>', methods=['GET'])
def get_match_details(match_id):
    rapid_key = os.getenv("RAPIDAPI_KEY")
    # Endpoint to fetch detailed scorecard & commentary data arrays
    url = f"https://cricket-highlights-api.p.rapidapi.com/match/{match_id}/details"
    headers = {
        "x-rapidapi-key": rapid_key,
        "x-rapidapi-host": "cricket-highlights-api.p.rapidapi.com"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return jsonify(res.json().get("data", {}))
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"message": "Detail payload empty"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
