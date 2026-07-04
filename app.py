import os
import sys
import json
import datetime
import litellm
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
# 2. LIVE SCORE STREAM (Replaces Serveo Tunnel)
# ---------------------------------------------------------------------
@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    # This serves the raw live cricket data that your n8n workflow fetches every minute
    mock_live_data = {
        "id": "t20_final_01",
        "match": "IND vs AUS",
        "status": "Innings Break",
        "batting_team": "IND",
        "score": "184/5",
        "overs": "20.0",
        "run_rate": "9.20",
        "top_scorer": "Kohli 82(53)",
        "top_bowler": "Starc 2/32"
    }
    return jsonify({"data": mock_live_data}), 200

# ---------------------------------------------------------------------
# 3. AI ARTICLE GENERATOR (Called post-match)
# ---------------------------------------------------------------------
@app.route('/mock-live', methods=['POST', 'GET'])
def run_ai_crew():
    if request.method == 'POST':
        match_data = request.get_json(silent=True) or {}
    else:
        match_data = {"id": "pending", "status": "no_incoming_payload"}

    llm = load_llm()

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
date: 2026-07-04
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

    match_id = match_data.get('id', 'pending')
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
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
