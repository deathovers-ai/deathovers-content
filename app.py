import os
import sys
import json
import datetime
import litellm

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

def load_llm():
    return LLM(
        model="groq/llama-3.3-70b-versatile",
        api_key=os.getenv("GROQ_API_KEY"),
        max_tokens=1000,
        temperature=0.1
    )

def main():
    # Load payload
    try:
        raw_payload = os.getenv("MATCH_DATA_PAYLOAD", "{}")
        match_data = json.loads(raw_payload)
    except Exception as e:
        print(f"Error parsing match payload: {e}")
        sys.exit(1)

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
date: 2026-07-03
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

    result = crew.kickoff()

    # ---------------------------------------------------------------------
    # UNIQUE FILE GENERATION
    # ---------------------------------------------------------------------
    # Use match ID if available, otherwise append a timestamp to ensure uniqueness
    match_id = match_data.get('id', 'pending')
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"src/content/posts/article-{match_id}-{timestamp}.md"
    
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(str(result))

    print(f"Successfully published match article to: {filename}")

if __name__ == "__main__":
    main()
