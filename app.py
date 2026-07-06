import os
import sys
import json
import time
import random
import datetime
from datetime import timezone
import requests
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify

# ---------------------------------------------------------------------
# BULLETPROOF BUGFIX: The LiteLLM Interceptor (Sync & Async)
# ---------------------------------------------------------------------
import litellm
_original_completion = litellm.completion
_original_acompletion = litellm.acompletion

def _patched_completion(*args, **kwargs):
    messages = kwargs.get("messages")
    if not messages and len(args) > 1:
        messages = args[1]
    if messages:
        for msg in messages:
            if isinstance(msg, dict):
                try: msg.pop("cache_breakpoint", None)
                except: pass
    return _original_completion(*args, **kwargs)

async def _patched_acompletion(*args, **kwargs):
    messages = kwargs.get("messages")
    if not messages and len(args) > 1:
        messages = args[1]
    if messages:
        for msg in messages:
            if isinstance(msg, dict):
                try: msg.pop("cache_breakpoint", None)
                except: pass
    return await _original_acompletion(*args, **kwargs)

litellm.completion = _patched_completion
litellm.acompletion = _patched_acompletion

from crewai import Agent, Task, Crew, Process

# Initialize Flask App
app = Flask(__name__)

# ---------------------------------------------------------------------
# HEALTH CHECK ROUTE
# ---------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "message": "DeathOvers AI Core Engine Running Live 24/7"}), 200

# ---------------------------------------------------------------------
# 2. THE HIGHLIGHTLY INTEGRATION PIPELINE
# ---------------------------------------------------------------------
@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    rapid_key = os.getenv("RAPIDAPI_KEY")
    force_mock = request.args.get('mock', 'false').lower() == 'true'
    
    if force_mock:
        return jsonify({
            "data": {
                "id": "mock_forced_test",
                "match": "IND vs AUS (Highlightly Forced Test)",
                "status": "Match in progress",
                "score": "312/4 (92.3 Ov)",
                "source": "Forced Test Diagnostic"
            }
        }), 200

    # PRODUCTION ENGINE: Accessing Highlightly's live data syndication grid
    if rapid_key:
        try:
            url = "https://cricket-api.p.rapidapi.com/matches"
            headers = {
                "x-rapidapi-key": rapid_key,
                "x-rapidapi-host": "cricket-api.p.rapidapi.com"
            }
            
            # Fetch matching parameters
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                payload = res.json()
                matches = payload.get("data", [])
                
                # Filter for active matches running live anywhere globally right now
                live_match = next((m for m in matches if m.get("status") in ["LIVE", "IN_PROGRESS", "LIVE - IN PROGRESS"]), None)
                
                # Backup: If no matches are live, pull the most current scheduled item
                if not live_match and matches:
                    live_match = matches[0]
                    
                if live_match:
                    team1 = live_match.get("team_home", {}).get("name", "Team 1")
                    team2 = live_match.get("team_away", {}).get("name", "Team 2")
                    score_text = live_match.get("score_display", "Match Preview / Upcoming")
                    
                    return jsonify({
                        "data": {
                            "id": f"hl_{live_match.get('id', 'match')}",
                            "match": f"{team1} vs {team2}",
                            "status": live_match.get("status", "Live Tracking"),
                            "score": score_text,
                            "source": "Highlightly Production API Engine"
                        }
                    }), 200
        except Exception as e:
            print(f"[Highlightly Core Connection Reset]: {str(e)}")

    # Core Safety net frame 
    return jsonify({
        "data": {
            "id": "mock_diagnostic_match",
            "match": "IND vs AUS (Test Mock)",
            "status": "Match in progress",
            "score": "284/3 (88.0 Ov)",
            "source": "Ecosystem Diagnostic Safety Net"
        }
    }), 200

# ---------------------------------------------------------------------
# 3. AI ARTICLE GENERATOR WITH STAGGERED EXECUTION
# ---------------------------------------------------------------------
@app.route('/mock-live', methods=['POST', 'GET'])
def run_ai_crew():
    if request.method == 'POST':
        match_data = request.get_json(silent=True) or {}
    else:
        match_data = {"id": "pending", "status": "no_incoming_payload"}

    target_model = "groq/llama-3.3-70b-versatile"

    data_scout = Agent(
        role="Lead Sports Performance Data Scout",
        goal="Extract high-leverage tactical anomalies from raw match metrics without hallucinating.",
        backstory="Veteran quantitative analyst specializing in high-frequency statistical trend identification.",
        llm=target_model
    )

    chief_editor = Agent(
        role="Senior Cricket Intelligence Editor",
        goal="Synthesize structured analytical findings into razor-sharp editorial journalism.",
        backstory="Chief Publisher for DeathOvers. Demands hard insights over derivative commentary.",
        llm=target_model
    )

    scouting_task = Task(
        description=f"Analyze match dataset: {json.dumps(match_data, indent=2)}",
        expected_output="An analytical metrics dossier detailing tactical turning points.",
        agent=data_scout
    )

    editorial_task = Task(
        description="""
Write a 300-word tactical match report. Must start exactly with this YAML frontmatter:
---
title: "[Catchy Title]"
date: 2026-07-06
category: press-box
targetEntity: "[Name]"
metricFocus: "[Metric]"
confidenceScore: 95
draft: false
---
""",
        expected_output="Raw markdown string starting with YAML frontmatter.",
        agent=chief_editor
    )

    crew = Crew(
        agents=[data_scout, chief_editor],
        tasks=[scouting_task, editorial_task],
        process=Process.sequential
    )

    try:
        time.sleep(2)
        result = crew.kickoff()
        article_text = str(result)
    except Exception as e:
        return jsonify({"status": "error", "message": f"CrewAI Execution Failed: {str(e)}"}), 500

    match_id = match_data.get('id', 'pending')
    timestamp = datetime.datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"src/content/posts/article-{match_id}-{timestamp}.md"

    return jsonify({
        "status": "success",
        "generated_at": timestamp,
        "target_file": filename,
        "data": article_text
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
