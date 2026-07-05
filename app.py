import os
import sys
import json
import datetime
import requests
import litellm
from bs4 import BeautifulSoup
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
# 1. HEALTH CHECK / KEEP-ALIVE ROUTE (For cron-job.org)
# ---------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "message": "DeathOvers AI Core Engine Running Live 24/7"
    }), 200

# ---------------------------------------------------------------------
# 2. LIVE SCORE STREAM (The Bulletproof Scraper)
# ---------------------------------------------------------------------
@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    try:
        # Disguise our server as a standard Chrome browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        }
        url = "https://www.cricbuzz.com/cricket-match/live-scores"
        
        # Fetch the page (Timeout set to 5 seconds to prevent server hanging)
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # BULLETPROOF SELECTOR: Look for ANY match container (handles T20s, Tests, Women's matches)
        matches = soup.select('div.cb-mtch-lst, div.cb-schdl')
        
        if not matches:
            return jsonify({"status": "error", "message": "No live matches found right now."}), 404

        # Grab the very first active match on the page
        first_match = matches[0]

        # Extract safely using broad fallbacks (Checks multiple possible Cricbuzz layouts)
        title_elem = first_match.find('h3') or first_match.find('a', class_='text-hvr-underline')
        title_text = title_elem.text.strip() if title_elem else "Unknown Match"

        score_elem = first_match.find('div', class_='cb-lv-scrs-col') or \
                     first_match.find('div', class_='cb-hmscg-bat-txt') or \
                     first_match.select_first('div[class*="bat-txt"]')
        score_text = score_elem.text.strip() if score_elem else "Score Pending"

        status_elem = first_match.find('div', class_='cb-text-live') or \
                      first_match.find('div', class_='cb-text-complete') or \
                      first_match.select_first('div[class*="cb-text-"]')
        status_text = status_elem.text.strip() if status_elem else "In Progress"

        live_data = {
            "id": f"match_{datetime.datetime.now().strftime('%Y%m%d')}",
            "match": title_text,
            "status": status_text,
            "score": score_text,
            "source": "Scraped via Render Engine"
        }

        return jsonify({"data": live_data}), 200

    except Exception as e:
        # If the scraper fails, it won't crash your server
        return jsonify({
            "status": "error", 
            "message": "Scraper failed to fetch data.", 
            "error_details": str(e)
        }), 500

# ---------------------------------------------------------------------
# 3. AI ARTICLE GENERATOR (Called post-match by n8n)
# ---------------------------------------------------------------------
@app.route('/mock-live', methods=['POST', 'GET'])
def run_ai_crew():
    # Grab incoming data payload safely (Handles GET fallback or incoming n8n POST data)
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
