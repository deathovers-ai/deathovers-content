from flask import Flask, jsonify, request
import datetime

app = Flask(__name__)

# Global in-memory state tracker simulating live database match-state storage
LIVE_MATCH_DB = {
    "active_match_id": "ipl_2026_gt_kkr",
    "status": "LIVE",               # LIVE, MID_INNINGS, CONCLUDED
    "innings": 1,                   # 1 or 2
    "currentPhaseId": "MID1",       # PP1, MID1, DEATH1, PP2, MID2, DEATH2
    "team1_name": "GT",
    "team2_name": "KKR",
    
    # Store dynamic logs for both innings independently to prevent pollution
    "innings1_logs": [
        {
            "phaseId": "PP1",
            "title": "Innings 1: Powerplay Phase",
            "metrics": {
                "rpo": "8.66",
                "boundaries": 8,
                "wickets": 1,
                "pressureIndex": "LOW"
            },
            "tacticalBlueprint": "GT capitalized cleanly on the hard ball. Starc struggled for swing, allowing the openers to line up hitting arcs over mid-on.",
            "winProbabilityDelta": 8.5
        },
        {
            "phaseId": "MID1",
            "title": "Innings 1: Middle Overs Spin Bind",
            "metrics": {
                "rpo": "6.80",
                "boundaries": 3,
                "wickets": 2,
                "pressureIndex": "CRITICAL"
            },
            "tacticalBlueprint": "KKR introduces Varun Chakravarthy. GT entering defensive matrix, prioritizing strike rotation to counter excessive turn from the northern end.",
            "winProbabilityDelta": -5.2
        }
    ],
    "innings2_logs": []
}

@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    """
    Standard endpoint wired to your n8n intake pipeline.
    Determines current phase routes based on active match state parameters.
    """
    # Isolate phase logs to reflect ONLY the active innings inside the UI deck
    active_logs = (
        LIVE_MATCH_DB["innings1_logs"] 
        if LIVE_MATCH_DB["innings"] == 1 
        else LIVE_MATCH_DB["innings2_logs"]
    )
    
    payload = {
        "matchMeta": {
            "matchId": LIVE_MATCH_DB["active_match_id"],
            "matchName": f"{LIVE_MATCH_DB['team1_name']} vs {LIVE_MATCH_DB['team2_name']}",
            "date": datetime.date.today().strftime("%Y-%m-%d"),
            "status": LIVE_MATCH_DB["status"],
        },
        "innings": LIVE_MATCH_DB["innings"],
        "currentPhaseId": LIVE_MATCH_DB["currentPhaseId"],
        "phaseLogs": active_logs
    }
    return jsonify(payload)

@app.route('/api/admin/update-phase', methods=['POST'])
def update_match_phase():
    """
    Control endpoint to simulate moving through the game's actual live phases.
    Accepts JSON body payload to update the in-memory engine.
    """
    data = request.json
    if not data:
        return jsonify({"error": "No payload provided"}), 400
        
    # Update core structural parameters if sent
    if "status" in data:
        LIVE_MATCH_DB["status"] = data["status"]
    if "innings" in data:
        LIVE_MATCH_DB["innings"] = data["innings"]
    if "currentPhaseId" in data:
        LIVE_MATCH_DB["currentPhaseId"] = data["currentPhaseId"]
        
    # Append a brand new telemetry slide to the active innings log list
    if "newLog" in data:
        log_target = "innings1_logs" if LIVE_MATCH_DB["innings"] == 1 else "innings2_logs"
        LIVE_MATCH_DB[log_target].append(data["newLog"])
        
    return jsonify({"message": "Telemetry engine updated successfully", "currentState": LIVE_MATCH_DB})

@app.route('/api/admin/reset-match', methods=['POST'])
def reset_match():
    """
    Resets the telemetry deck to clean template basics for game initializations.
    """
    global LIVE_MATCH_DB
    LIVE_MATCH_DB = {
        "active_match_id": "ipl_2026_gt_kkr",
        "status": "LIVE",
        "innings": 1,
        "currentPhaseId": "PP1",
        "team1_name": "GT",
        "team2_name": "KKR",
        "innings1_logs": [],
        "innings2_logs": []
    }
    return jsonify({"message": "Telemetry memory track cleared completely."})

if __name__ == '__main__':
    # Bind to 0.0.0.0 and dynamically match environment port constraints for Render deployment
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
