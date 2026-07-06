import os
import datetime
from datetime import timezone
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
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
            matches = res.json().get("data", [])
            
            # 1. Look for live matches
            live_match = next((m for m in matches if m.get("state", {}).get("description") == "In play"), None)
            
            if live_match:
                return jsonify({
                    "mode": "live",
                    "data": {
                        "id": live_match.get("id"),
                        "match": f"{live_match.get('homeTeam', {}).get('name')} vs {live_match.get('awayTeam', {}).get('name')}",
                        "score": live_match.get("state", {}).get("teams", {}),
                        "status": "In play",
                        "homeLogo": live_match.get("homeTeam", {}).get("logo"),
                        "awayLogo": live_match.get("awayTeam", {}).get("logo")
                    }
                })
            
            # 2. Fallback: Include names for upcoming matches
            upcoming = [
                {
                    "id": m.get("id"),
                    "matchName": f"{m.get('homeTeam', {}).get('name')} vs {m.get('awayTeam', {}).get('name')}",
                    "startTime": m.get("startTime"),
                    "venue": m.get("venue", {}).get("name", "TBD")
                } for m in matches[:3] # Limit to top 3 upcoming matches today
            ]
            return jsonify({"mode": "scheduled", "data": {"upcoming": upcoming}})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"mode": "empty", "data": {}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
