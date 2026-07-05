import os
import sys
import json
import datetime
import requests
import litellm
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify

# ---------------------------------------------------------------------
# BULLETPROOF BUGFIX: The LiteLLM Interceptor (Sync & Async)
# ---------------------------------------------------------------------
_original_completion = litellm.completion
_original_acompletion = litellm.acompletion

def _patched_completion(*args, **kwargs):
    messages = kwargs.get("messages")
    if not messages and len(args) > 1:
        messages = args[1]
    if messages:
        for msg in messages:
            if isinstance(msg, dict):
                msg.pop("cache_breakpoint", None)
    return _original_completion(*args, **kwargs)

async def _patched_acompletion(*args, **kwargs):
    messages = kwargs.get("messages")
    if not messages and len(args) > 1:
        messages = args[1]
    if messages:
        for msg in messages:
            if isinstance(msg, dict):
                msg.pop("cache_breakpoint", None)
    return await _original_acompletion(*args, **kwargs)

litellm.completion = _patched_completion
litellm.acompletion = _patched_acompletion

from crewai import Agent, Task, Crew, Process, LLM

# Initialize Flask App
app = Flask(__name__)

def load_llm():
    return LLM(
        model="groq/llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        max_tokens=1000,
        temperature=0.1
    )

# ---------------------------------------------------------------------
# 1. HEALTH CHECK / KEEP-ALIVE ROUTE
# ---------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "message": "DeathOvers AI Core Engine Running Live 24/7"
    }), 200

# ---------------------------------------------------------------------
# 2. LIVE SCORE STREAM (The Secret Cricbuzz J2ME Backdoor)
# ---------------------------------------------------------------------
@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    try:
        # This is Cricbuzz's legacy XML feed for old mobile phones. 
        # Zero JavaScript. Zero Cloudflare blocks. Real-time updates.
        url = "http://synd.cricbuzz.com/j2me/1.0/livematches.xml"
        
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        
        # Parse the raw XML data
        root = ET.fromstring(response.content)
        matches = root.findall('match')
        
        if not matches:
            return jsonify({"status": "error", "message": "No live matches found right now."}), 404

        # Prioritize finding a match that is actually in progress right now
        live_match = None
        for match in matches:
            state = match.find('state')
            if state is not None and state.get('mchState') in ['inprogress', 'innings break', 'rain', 'stump', 'tea']:
                live_match = match
                break
                
        # If no matches are currently being played, just grab the first one on the list
        if not live_match:
             live_match = matches[0]

        # Extract Match Data safely from XML nodes
        match_title = live_match.get('mchDesc', 'Live Match')
        
        state_node = live_match.find('state')
        status = state_node.get('status', 'In Progress') if state_node is not None else "In Progress"
        
        # Extract the actual Live Score numbers
        score_str = "Score pending"
        mscr_node = live_match.find('mscr')
        if mscr_node is not None:
            bat_node = mscr_node.find('btTm')
            if bat_node is not None:
                team_name = bat_node.get('sName', 'Team')
                inngs = bat_node.find('Inngs')
                if inngs is not None:
                    runs = inngs.get('run', '0')
                    wkts = inngs.get('wkts', '0')
                    ovs = inngs.get('Ovs', '0')
                    score_str = f"{team_name} {runs}/{wkts} ({ovs} Ovs)"

        live_data = {
            "id": f"match_{datetime.datetime.now().strftime('%Y%m%d%H%M')}",
            "match": match_title,
            "status": status,
            "score": score_str,
            "source": "Cricbuzz XML Datapipe"
        }

        return jsonify({"data": live_data}), 200

    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": "XML Feed failed to fetch data.", 
            "error_details": str(e)
        }), 500

# ---------------------------------------------------------------------
# 3. AI ARTICLE GENERATOR (Called post-match by n8n)
# ---------------------------------------------------------------------
@app.route('/mock-live', methods=['POST', 'GET'])
def run_ai_crew():
    # Grab incoming data payload safely
    if request.method == 'POST':
        match_data = request.get_json(silent=True) or {}
    else:
        match_data = {"id": "pending", "status": "no_incoming_payload"}

    llm = load_llm()

    # Define Agents
    data_scout = Agent(
        role="Lead Sports Performance Data Scout",
        goal="Extract high-leverage tactical anomalies from raw match metrics.",
        backstory="Veteran cricket quantitative analyst.",
        llm=llm
    )

    chief_editor = Agent(
        role="Senior Cricket Intelligence Editor",
        goal="Translate raw data anomalies into gripping sports journalism.",
        backstory="Lead editor for DeathOvers. Sharp and authoritative.",
        llm=llm
    )

    # Define Tasks
    scouting_task = Task(
        description=f"Analyze match dataset: {json.dumps(match_data, indent=2)}",
        expected_output="A structured tactical brief.",
        agent=data_scout
    )

    editorial_task = Task(
        description="""
Write a 300-word tactical match report.
Must start with:
---
title: "[Catchy Title]"
date: 2026-07-05
category: press-box
targetEntity: "[Name]"
metricFocus: "[Metric]"
confidenceScore: 95
draft: false
---
""",
        expected_output="Raw markdown string starting with YAML frontmatter.",
        agent=chief_editor,
        context=[scouting_task]
    )

    # Run Crew
    crew = Crew(
        agents=[data_scout, chief_editor],
        tasks=[scouting_task, editorial_task],
        process=Process.sequential
    )

    try:
        result = crew.kickoff()
        article_text = str(result)
    except Exception as e:
        return jsonify({"status": "error", "message": f"CrewAI Execution Failed: {str(e)}"}), 500

    # Unique File Tracking Data Payload
    match_id = match_data.get('id', 'pending')
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"src/content/posts/article-{match_id}-{timestamp}.md"

    # Return structured output payload right back to n8n
    return jsonify({
        "status": "success",
        "generated_at": timestamp,
        "target_file": filename,
        "data": article_text
    }), 200

if __name__ == "__main__":
    # Render binds dynamically to the system environment PORT variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
