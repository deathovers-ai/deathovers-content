import os
import json
import logging
from datetime import datetime
from crewai import Agent, Task, Crew, LLM

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# These variables now pull directly from the environment mapped in your YAML
def build_llm_chain():
    return [
        ("gemini", "gemini/gemini-2.5-flash-lite", "GEMINI_API_KEY"),
        ("groq", "groq/llama-3.3-70b-versatile", "GROQ_API_KEY"),
        ("openrouter", "openrouter/meta-llama/llama-3.3-70b-instruct", "OPENROUTER_API_KEY"),
    ]

# Error handling helper
RETRYABLE_MARKERS = ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "503", "429", "overloaded", "quota")

def is_retryable(exc: Exception) -> bool:
    msg = str(exc)
    return any(marker in msg for marker in RETRYABLE_MARKERS)

# Load data from n8n
match_data_raw = os.environ.get("MATCH_DATA", "{}")
match_data = json.loads(match_data_raw)

# --- AGENT FACTORY ---
def build_crew(llm):
    data_scout = Agent(
        role="Lead Cricket Performance Analyst",
        goal="Isolate high-leverage data anomalies within raw scorecard structures",
        backstory="20-year veteran data scientist specializing in cricket metrics.",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    chief_editor = Agent(
        role="Senior Editorial Director - DeathOvers",
        goal="Synthesize statistical briefs into elite sports journalism",
        backstory="Chief Editor of DeathOvers, competing with top-tier outlets.",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    scouting_task = Task(
        description=f"Analyze match data: {json.dumps(match_data)}",
        expected_output="A factual data brief highlighting the key tactical insight.",
        agent=data_scout
    )

    editorial_task = Task(
        description="Write a 300-word article based on the brief.",
        expected_output="A complete markdown article with frontmatter.",
        agent=chief_editor,
        context=[scouting_task]
    )

    return Crew(agents=[data_scout, chief_editor], tasks=[scouting_task, editorial_task], verbose=True)

# --- FALLBACK LOGIC ---
def run_crew_with_fallback():
    provider_chain = build_llm_chain()
    
    for provider_name, model_string, env_var_name in provider_chain:
        api_key = os.environ.get(env_var_name)
        
        if not api_key:
            logger.warning(f"Skipping '{provider_name}': {env_var_name} not set in environment.")
            continue

        try:
            logger.info(f"Attempting task with: {provider_name}")
            llm = LLM(model=model_string, api_key=api_key)
            crew = build_crew(llm)
            result = crew.kickoff()
            logger.info(f"Success on provider: {provider_name}")
            return result
        except Exception as e:
            if is_retryable(e):
                logger.warning(f"'{provider_name}' failed retryably: {e}")
                continue
            else:
                logger.error(f"Non-retryable error on '{provider_name}': {e}")
                raise e
    raise RuntimeError("All LLM providers failed.")

# --- EXECUTION ---
if __name__ == "__main__":
    result = run_crew_with_fallback()
    
    # Save logic
    article_text = str(result)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"content/posts/{timestamp}-article.md"
    os.makedirs("content/posts", exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(article_text)
    print(f"Article saved: {filename}")
