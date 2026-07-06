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
# LOCAL SCAPER MODULES (Maintained for Local Testing Execution Only)
# ---------------------------------------------------------------------
def _find_balanced_json(text: str, key: str, start: int = 0) -> str | None:
    needle = f'"{key}":{{'
    idx = text.find(needle, start)
    if idx == -1:
        needle2 = f'"{key}": {{'
        idx = text.find(needle2, start)
        if idx == -1: return None
        brace_start = idx + len(needle2) - 1
    else:
        brace_start = idx + len(needle) - 1

    depth, in_string, escape, i, n = 0, False, False, brace_start, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if escape: escape = False
            elif ch == "\\": escape = True
            elif ch == '"': in_string = False
        else:
            if ch == '"': in_string = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: return text[brace_start : i + 1]
        i += 1
    return None

def _unescape_next_f_string(raw: str) -> str:
    try: return json.loads(f'"{raw}"')
    except: return raw.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")

def extract_next_f_chunks(html: str) -> list[str]:
    chunks, marker, pos = [], "self.__next_f.push([1,", 0
    while True:
        start = html.find(marker, pos)
        if start == -1: break
        q = html.find('"', start + len(marker))
        if q == -1: break
        i, n, escape = q + 1, len(html), False
        while i < n:
            ch = html[i]
            if escape: escape = False
            elif ch == "\\": escape = True
            elif ch == '"': break
            i += 1
        chunks.append(_unescape_next_f_string(html[q + 1 : i]))
        pos = i + 1
    return chunks

def extract_homepage_matches(html: str) -> list[dict]:
    chunks = extract_next_f_chunks(html)
    results, seen_ids = [], set()
    for chunk in chunks:
        pos = 0
        while True:
            block = _find_balanced_json(chunk, "matchInfo", pos)
            if block is None: break
            try: 
                match_info = json.loads(block)
                mid = match_info.get("matchId")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    results.append(match_info)
            except: pass
            pos = chunk.find(block) + len(block)
    return results

def extract_live_match_miniscore(html: str) -> dict | None:
    for chunk in extract_next_f_chunks(html):
        cpd_block = _find_balanced_json(chunk, "commentaryPageData")
        if not cpd_block: continue
        try:
            cpd = json.loads(cpd_block)
            if "miniscore" in cpd: return cpd["miniscore"]
        except: continue
    return None

# ---------------------------------------------------------------------
# 1. HEALTH CHECK ROUTE
# ---------------------------------------------------------------------
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "online", "message": "DeathOvers AI Core Engine Running Live 24/7"}), 200

# ---------------------------------------------------------------------
# 2. FAILOVER ENGINE: PRODUCTION OFFICIAL API CEILING
# ---------------------------------------------------------------------
@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    api_key = os.getenv("CRICKETDATA_API_KEY")
    
    # --- PRO-MODE LAYER: LIVE API SYNDICATION (Official CricketData.org Mapping) ---
    if api_key:
        try:
            url = f"https://api.cricketdata.org/v1/currentMatches?apikey={api_key}"
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                payload = res.json()
                matches = payload.get("data", [])
                
                # Scan for any actively running live match block
                live_match = next((m for m in matches if "matchStarted" in m and m.get("matchStarted")), None)
                if not live_match and matches:
                    live_match = matches[0]
                    
                if live_match:
                    score_array = live_match.get("score", [])
                    score_text = "Innings Break / Preview"
                    
                    # Parse CricketData.org's native score entry layout safely
                    if score_array and isinstance(score_array, list):
                        s = score_array[0]
                        score_text = f"{s.get('r', 0)}/{s.get('w', 0)} ({s.get('o', 0)} Ov) - {s.get('inning', 'Inning 1')}"

                    return jsonify({
                        "data": {
                            "id": f"api_{live_match.get('id', 'match')}",
                            "match": live_match.get("name", "Live Match Summary"),
                            "status": live_match.get("status", "In Progress"),
                            "score": score_text,
                            "source": "Production CricketData.org API"
                        }
                    }), 200
        except Exception as e:
            print(f"[API Layer Failure] Redirecting to Local Proxy Scraper: {str(e)}")

    # --- FALLBACK LAYER: RESIDENTIAL LOCAL SCRAPER MATRIX ---
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        home_html = requests.get("https://www.cricbuzz.com/", headers=headers, timeout=6).text
        matches = extract_homepage_matches(home_html)
        
        active_match_id = None
        match_title = "Live Match"
        for m in matches:
            if m.get("state") in ["inprogress", "innings break", "rain", "stump", "tea"]:
                active_match_id = m.get("matchId")
                t1 = m.get("team1", {}).get("teamSName", "Team1")
                t2 = m.get("team2", {}).get("teamSName", "Team2")
                match_title = f"{t1} vs {t2}"
                break
        
        if active_match_id:
            match_url = f"https://www.cricbuzz.com/live-cricket-scores/{active_match_id}/match"
            match_html = requests.get(match_url, headers=headers, timeout=6).text
            miniscore = extract_live_match_miniscore(match_html)
            
            if miniscore:
                bat_team = miniscore.get("batTeam", {})
                score_str = f"{bat_team.get('teamScore', 0)}/{bat_team.get('teamWkts', 0)} ({miniscore.get('overs', 0)})"
                return jsonify({
                    "data": {
                        "id": f"match_{active_match_id}",
                        "match": match_title,
                        "status": miniscore.get("status", "In Progress"),
                        "score": score_str,
                        "source": "Local System Scraper Proxy"
                    }
                }), 200
    except:
        pass

    return jsonify({
        "status": "error",
        "message": "All deployment pipelines exhausted. Verify server network configurations or API allowances.",
        "diagnostics": "Ecosystem Subnet Firewall Block Active on Infrastructure Nodes. Inject valid CRICKETDATA_API_KEY environment token to unlock production."
    }), 404

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
