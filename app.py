import os
import datetime
from datetime import timezone
import requests
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    rapid_key = os.getenv("RAPIDAPI_KEY")
    today_date = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Highlightly endpoint for cricket matches
    url = f"https://cricket-highlights-api.p.rapidapi.com/matches?date={today_date}"
    headers = {
        "x-rapidapi-key": rapid_key,
        "x-rapidapi-host": "cricket-highlights-api.p.rapidapi.com"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            matches = res.json().get("data", [])
            
            # Logic: Identify if any match is currently "In play"
            live_match = next((m for m in matches if m.get("state", {}).get("description") == "In play"), None)
            
            if live_match:
                return jsonify({
                    "mode": "live",
                    "data": {
                        "id": live_match.get("id"),
                        "match": f"{live_match.get('homeTeam', {}).get('name')} vs {live_match.get('awayTeam', {}).get('name')}",
                        "score": live_match.get("state", {}).get("teams", {}),
                        "status": "In play",
                        "homeLogo": live_match.get("homeTeam", {}).get("logo"), # Logo extraction
                        "awayLogo": live_match.get("awayTeam", {}).get("logo")
                    }
                })
            
            # Fallback: Return upcoming matches if nothing is live
            upcoming = [
                {
                    "id": m.get("id"),
                    "homeLogo": m.get("homeTeam", {}).get("logo"),
                    "awayLogo": m.get("awayTeam", {}).get("logo"),
                    "startTime": m.get("startTime"),
                    "venue": m.get("venue", {}).get("name", "TBD")
                } for m in matches[:5]
            ]
            return jsonify({"mode": "scheduled", "data": {"upcoming": upcoming}})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"mode": "empty", "data": {}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
