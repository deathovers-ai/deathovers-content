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
# RSC EXTRACTION ENGINE (Internalized for Monolithic Deployment)
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
# 2. FAILOVER ENGINE WITH DATA NORMALIZATION
# ---------------------------------------------------------------------
@app.route('/api/live-scores', methods=['GET'])
def get_live_scores():
    # Production Browser-Spoofing Matrix
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "max-age=0",
        "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    session = requests.Session()
    last_error_log = ""

    # --- PRIORITY 1: NEXT.JS RSC EXTRACTION (High Fidelity) ---
    try:
        home_res = session.get("https://www.cricbuzz.com/", headers=headers, timeout=8)
        home_html = home_res.text
        
        # Check if Cloudflare challenged us
        if "Just a moment..." in home_html or "cloudflare" in home_html.lower():
            last_error_log += "[Priority 1] Blocked by Cloudflare Security Layer. "
        else:
            matches = extract_homepage_matches(home_html)
            active_match_id = None
            match_title = "Live Match"
            
            # Match scanning state array
            for m in matches:
                if m.get("state") in ["inprogress", "innings break", "rain", "stump", "tea", "preview"]:
                    active_match_id = m.get("matchId")
                    t1 = m.get("team1", {}).get("teamSName", "Team1")
                    t2 = m.get("team2", {}).get("teamSName", "Team2")
                    match_title = f"{t1} vs {t2}"
                    break
            
            if active_match_id:
                match_url = f"https://www.cricbuzz.com/live-cricket-scores/{active_match_id}/match"
                match_html = session.get(match_url, headers=headers, timeout=8).text
                miniscore = extract_live_match_miniscore(match_html)
                
                if miniscore:
                    bat_team = miniscore.get("batTeam", {})
                    score_str = f"{bat_team.get('teamScore', 0)}/{bat_team.get('teamWkts', 0)} ({miniscore.get('overs', 0)})"
                    crr = miniscore.get("currentRunRate", 0)
                    recent = miniscore.get("recentOvsStats", "")
                    rich_score = f"{score_str} | CRR: {crr} | Recent: {recent}"

                    return jsonify({
                        "data": {
                            "id": f"match_{active_match_id}",
                            "match": match_title,
                            "status": miniscore.get("status", "In Progress"),
                            "score": rich_score,
                            "source": "Priority 1: RSC Extraction"
                        }
                    }), 200
            else:
                last_error_log += "[Priority 1] No active matches found in the active layout array. "
    except Exception as e:
        last_error_log += f"[Priority 1 Error] {str(e)}. "

    # --- PRIORITY 2: THE LEGACY CRICBUZZ BACKDOOR ---
    try:
        fallback_url = "http://synd.cricbuzz.com/j2me/1.0/livematches.xml"
        # Legacy route uses lighter mobile headers
        mobile_headers = {"User-Agent": "NokiaX2-01/5.0 (08.71) Profile/MIDP-2.1 Configuration/CLDC-1.1 Mozilla/5.0"}
        res = session.get(fallback_url, headers=mobile_headers, timeout=8)
        
        if res.status_code == 200 and b"match" in res.content:
            root = ET.fromstring(res.content)
            matches = root.findall('match')
            
            live_match = next((m for m in matches if m.find('state') is not None and m.find('state').get('mchState') in ['inprogress', 'innings break', 'preview']), None)
            live_match = live_match or (matches[0] if matches else None)

            if live_match is not None:
                score_str = "Score Pending"
                mscr = live_match.find('mscr')
                if mscr is not None and mscr.find('btTm') is not None:
                    bt = mscr.find('btTm')
                    inngs = bt.find('Inngs')
                    if inngs is not None:
                        score_str = f"{bt.get('sName', 'Team')} {inngs.get('run','0')}/{inngs.get('wkts','0')} ({inngs.get('Ovs','0')} Ov)"
                
                return jsonify({
                    "data": {
                        "id": f"cb_backdoor_{datetime.datetime.now().strftime('%Y%m%d%H%M')}",
                        "match": live_match.get('mchDesc', 'Live Match'),
                        "status": live_match.find('state').get('status', 'In Progress') if live_match.find('state') is not None else 'In Progress',
                        "score": score_str,
                        "source": "Priority 2: Cricbuzz Legacy XML"
                    }
                }), 200
            else:
                last_error_log += "[Priority 2] XML empty or malformed match headers. "
        else:
            last_error_log += f"[Priority 2] Received bad status code: {res.status_code}. "
    except Exception as e:
        last_error_log += f"[Priority 2 Error] {str(e)}. "

    # --- ALL PIPELINES EXHAUSTED: DIAGNOSTIC RETRIEVAL ---
    return jsonify({
        "status": "error",
        "message": "No live matches found or all pipelines blocked.",
        "diagnostics": last_error_log
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
