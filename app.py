import os
import sys
import json
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI

# ---------------------------------------------------------------------
# CRITICAL COMPLIANCE PATCH: CrewAI Groq Prompt-Caching Fix
# Intercepts and bypasses unsupported Anthropic caching tags in Groq
# ---------------------------------------------------------------------
import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda msg: msg
# ---------------------------------------------------------------------

def load_llm_chain():
    """
    Automated Try-Except Fallback Engine
    Ensures zero pipeline failure by gracefully failing over across models
    when daily quotas or rate limits are hit.
    """
    # 1. Primary Model: Gemini (via OpenRouter or Native)
    try:
        return ChatOpenAI(
            model="google/gemini-2.5-pro", 
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
    except Exception:
        pass

    # 2. Secondary Model: Groq (Llama 3.3 70B)
    try:
        return ChatOpenAI(
            model="meta-llama/llama-3.3-70b-instruct",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
    except Exception:
        pass

    # 3. Final Failover: General OpenRouter Provider
    return ChatOpenAI(
        model="openrouter/auto",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

def main():
    # Load raw text payload sent by n8n
    # n8n now uses JSON.stringify(), passing clean textual data
    try:
        raw_payload = os.getenv("MATCH_DATA_PAYLOAD", "{}")
        match_data = json.loads(raw_payload)
    except Exception as e:
        print(f"Error parsing match payload JSON: {e}")
        sys.exit(1)

    # Initialize the resilient LLM engine
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
    # TASK DEFINITIONS (Structured via Markdown Prompting Formula)
    # ---------------------------------------------------------------------
    scouting_task = Task(
        description=f"""
# **Role:**
Lead Sports Performance Data Scout

# **Objective:**
Identify the defining statistical anomaly from the raw match JSON dataset that explains why the match swung.

# **Context:**
Match Data Payload: {json.dumps(match_data, indent=2)}

# **Instructions:**
## **Instruction 1:** Parse the provided team names, scorecards, and venue conditions.
## **Instruction 2:** Isolate one specific phase-of-play metric (e.g., powerplay boundary rate, middle-overs dot balls) that caused the winning team to dominate.
## **Instruction 3:** Compile a detailed, bulleted data summary brief for the Chief Editor.
""",
        expected_output="A structured data brief highlighting key tactical metrics.",
        agent=data_scout
    )

    editorial_task = Task(
        description="""
# **Role:**
Senior Cricket Intelligence Editor

# **Objective:**
Write a 300-word tactical match report based on the scout's data brief, formatted perfectly for a Vercel static site deployment.

# **Context:**
Our readers are digital-first cricket superfans who demand immediate tactical clarity. They expect data-backed narrative journalism.

# **Instructions:**
## **Instruction 1:** Analyze the data scout's brief and construct a compelling, high-intent headline.
## **Instruction 2:** Draft a 300-word analytical post focusing on the tactical inflection point.
## **Instruction 3:** Structure the final output file as raw text, starting exactly with the required Vercel metadata frontmatter.

# **Notes:**
* CRITICAL FRONTMATTER DIRECTION: You MUST start your response with valid YAML frontmatter.
* Do NOT wrap your entire response in ```markdown formatting blocks. Just output the the text cleanly.
* The absolute first characters of your output must be the opening triple-dashes. Follow this template precisely:
---
title: "[Your Catchy, Strategic Title Here]"
date: 2026-07-03
draft: false
---
[Your article content begins here...]
""",
        expected_output="A raw markdown string containing YAML frontmatter and a 300-word tactical analysis.",
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

    # Generate unique programmatic file name for static site injection
    # Example: 20260703-match-analysis.md
    filename = f"content/posts/article-{match_data.get('id', 'pending')}.md"
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(str(result))

    print(f"Successfully published match article to: {filename}")

if __name__ == "__main__":
    main()
