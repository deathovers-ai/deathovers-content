import os
import datetime
from datetime import timezone
import time
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- CACHE CONFIGURATION ---
cache = {
    "data": None,
    "timestamp": 0
}
CACHE_DURATION = 60  # Cache memory lasts for 60 seconds

@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    current_time = time.time()
    
    # 1. Check if we have fresh data in the cache shield
    if cache["data"] and (current_time - cache["timestamp"] < CACHE_DURATION):
        return jsonify(cache["data"])

    # 2. If cache is empty or expired, hit the RapidAPI
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
            live_match = next((m for m in matches if m.get("state", {}).get("description") == "In play"), None)
            
            # Prepare the response payload
            response_payload = {}
            
            if live_match:
                response_payload = {
                    "mode": "live",
                    "data": {
                        "id": live_match.get("id"),
                        "match": f"{live_match.get('homeTeam', {}).get('name')} vs {live_match.get('awayTeam', {}).get('name')}",
                        "score": live_match.get("state", {}).get("teams", {}),
                        "status": "In play",
                        "homeLogo": live_match.get("homeTeam", {}).get("logo"),
                        "awayLogo": live_match.get("awayTeam", {}).get("logo")
                    }
                }
            else:
                upcoming = [
                    {
                        "id": m.get("id"),
                        "matchName": f"{m.get('homeTeam', {}).get('name')} vs {m.get('awayTeam', {}).get('name')}",
                        "startTime": m.get("startTime"),
                        "venue": m.get("venue", {}).get("name", "TBD")
                    } for m in matches[:3]
                ]
                response_payload = {"mode": "scheduled", "data": {"upcoming": upcoming}}

            # 3. Save to cache and return
            cache["data"] = response_payload
            cache["timestamp"] = current_time
            return jsonify(response_payload)
            
    except Exception as e:
        # If RapidAPI fails, try to serve stale cache data if we have it
        if cache["data"]:
            return jsonify(cache["data"])
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"mode": "empty", "data": {}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
