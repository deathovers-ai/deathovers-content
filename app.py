import os
import sys
import json

# ---------------------------------------------------------------------
# BUGFIX: The Monkey Patch
# This MUST execute before CrewAI is imported. It stops CrewAI from 
# injecting Anthropic-specific cache tags into our Groq payload.
# ---------------------------------------------------------------------
import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda msg: msg
# ---------------------------------------------------------------------

from crewai import Agent, Task, Crew, Process, LLM

def load_llm():
    return LLM(
        model="groq/llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        max_tokens=1000,
        temperature=0.1
    )

def main():
    # 1. Load the exact payload sent from the GitHub Action YAML
    try:
        raw_payload = os.getenv("MATCH_DATA_PAYLOAD", "{}")
        match_data = json.loads(raw_payload)
    except Exception as e:
        print(f"Error parsing match payload JSON: {e}")
        sys.exit(1)

    llm = load_llm()

    # ---------------------------------------------------------------------
    # AGENT DEFINITIONS
    # ---------------------------------------------------------------------
    data_scout = Agent(
        role="Lead Sports Performance Data Scout",
        goal="Extract high-leverage tactical anomalies from raw match metrics.",
        backstory="""You are a veteran cricket quantitative analyst. You look for 
        inflection points, tactical phase shifts, and non-obvious player matchups.""",
        verbose=True,
        llm=llm
    )

    chief_editor = Agent(
        role="Senior Cricket Intelligence Editor",
        goal="Translate raw data anomalies into gripping, analytical sports journalism.",
        backstory="""You are the lead editor for DeathOvers. Your writing style is sharp, 
        authoritative, and tailored for fantasy cricket tacticians and superfans. You explain 
        WHY matches are won, using data cleanly without fluff.""",
        verbose=True,
        llm=llm
    )

    # ---------------------------------------------------------------------
    # TASK DEFINITIONS
    # ---------------------------------------------------------------------
    scouting_task = Task(
        description=f"""
Analyze this incoming match dataset:
{json.dumps(match_data, indent=2)}

Instructions:
1. Parse the scorecard and match context.
2. Isolate ONE specific phase-of-play metric that caused the winning team to dominate.
3. Compile a detailed, bulleted data summary brief for the Editor.
""",
        expected_output="A structured data brief highlighting key tactical metrics.",
        agent=data_scout
    )

    editorial_task = Task(
        description="""
Write a 300-word tactical match report based on the scout's data brief.

CRITICAL INSTRUCTIONS FOR ASTRO.JS:
1. You MUST start your response with valid YAML frontmatter.
2. The absolute first characters of your output must be `---`.
3. Do NOT wrap the response in markdown code blocks (like ```markdown). 
4. You MUST include the exact fields shown below:

---
title: "[Catchy, Strategic Title Here]"
date: 2026-07-03
category: press-box
targetEntity: "[Player/Team Name]"
metricFocus: "[The core metric you focused on]"
confidenceScore: 95
draft: false
---

[Your 300-word tactical article content begins immediately here...]
""",
        expected_output="Raw markdown string starting strictly with YAML frontmatter.",
        agent=chief_editor,
        context=[scouting_task]
    )

    # ---------------------------------------------------------------------
    # EXECUTION ENGINE
    # ---------------------------------------------------------------------
    crew = Crew(
        agents=[data_scout, chief_editor],
        tasks=[scouting_task, editorial_task],
        process=Process.sequential,
        verbose=True
    )

    result = crew.kickoff()

    # ---------------------------------------------------------------------
    # FILE GENERATION
    # ---------------------------------------------------------------------
    match_id = match_data.get('id', 'pending')
    filename = f"src/content/posts/article-{match_id}.md"
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(str(result))

    print(f"Successfully published match article to: {filename}")

if __name__ == "__main__":
    main()
