import os
import sys
import json
from crewai import Agent, Task, Crew, Process, LLM

# ---------------------------------------------------------------------
# CRITICAL COMPLIANCE PATCH: CrewAI Groq Prompt-Caching Fix
# ---------------------------------------------------------------------
import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda msg: msg
# ---------------------------------------------------------------------

def load_llm_chain():
    """
    Switched to OpenRouter's 100% FREE Gemini model to bypass 402 account limits.
    """
    return LLM(
        model="openrouter/google/gemini-2.0-flash-exp:free", 
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        max_tokens=800
    )

def main():
    try:
        raw_payload = os.getenv("MATCH_DATA_PAYLOAD", "{}")
        match_data = json.loads(raw_payload)
    except Exception as e:
        print(f"Error parsing match payload JSON: {e}")
        sys.exit(1)

    llm = load_llm_chain()

    # ---------------------------------------------------------------------
    # AGENT DEFINITIONS
    # ---------------------------------------------------------------------
    data_scout = Agent(
        role="Lead Sports Performance Data Scout",
        goal="Extract high-leverage tactical anomalies from raw match metrics.",
        backstory="""You are a veteran cricket quantitative analyst. You don't care about 
        generic scores; you look for inflection points, tactical phase shifts, and non-obvious 
        player matchups in the data feed.""",
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
# **Role:** Lead Sports Performance Data Scout
# **Objective:** Identify the defining statistical anomaly from the raw match dataset.
# **Context:** Match Data: {json.dumps(match_data, indent=2)}
# **Instructions:**
1. Parse the provided team names and scorecards.
2. Isolate one specific phase-of-play metric that caused the win.
3. Compile a bulleted data summary brief.
""",
        expected_output="A structured data brief highlighting key tactical metrics.",
        agent=data_scout
    )

    editorial_task = Task(
        description="""
# **Role:** Senior Cricket Intelligence Editor
# **Objective:** Write a 300-word tactical match report for an Astro static site.

# **Instructions:**
1. Analyze the scout's brief and construct a compelling headline.
2. Draft a 300-word analytical post.
3. Start the output exactly with the required Astro metadata frontmatter.

# **Notes:**
* You MUST start your response with valid YAML frontmatter.
* The absolute first characters of your output must be `---`.
* Do NOT use markdown code blocks to wrap the response.
* You MUST include the exact fields shown below:

---
title: "[Your Catchy, Strategic Title Here]"
date: 2026-07-03
category: press-box
targetEntity: "[Name of the Key Player or Team]"
metricFocus: "[The core metric you focused on]"
confidenceScore: 95
draft: false
---
[Your article content begins here...]
""",
        expected_output="Raw markdown string with YAML frontmatter and a 300-word analysis.",
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

    filename = f"src/content/posts/article-{match_data.get('id', 'pending')}.md"
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(str(result))

    print(f"Successfully published match article to: {filename}")

if __name__ == "__main__":
    main()
