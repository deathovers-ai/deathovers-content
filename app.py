import os
import json
import logging
from datetime import datetime
from crewai import Agent, Task, Crew, LLM

# --- THE CREWAI GROQ FIX (Monkey Patch) ---
# This safely intercepts CrewAI's caching mechanism to strip 
# the unsupported Anthropic tags before they reach Groq.
import crewai.llms.cache as _crewai_cache
_crewai_cache.mark_cache_breakpoint = lambda msg: msg
# ------------------------------------------

# Configure logging to be highly visible
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
def build_llm_chain():
    return [
        ("gemini", "gemini/gemini-2.5-flash-lite", "GEMINI_API_KEY"),
        ("groq", "groq/llama-3.3-70b-versatile", "GROQ_API_KEY"),
        ("openrouter", "openrouter/meta-llama/llama-3.3-70b-instruct", "OPENROUTER_API_KEY"),
    ]

# Expanded error markers to catch CrewAI's internal logging format
RETRYABLE_MARKERS = [
    "UNAVAILABLE", "RESOURCE_EXHAUSTED", "503", "429", 
    "overloaded", "quota", "An unknown error occurred", "Task Failure"
]

def is_retryable(error_msg: str) -> bool:
    msg_str = str(error_msg)
    return any(marker in msg_str for marker in RETRYABLE_MARKERS)

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

# --- AGGRESSIVE FALLBACK LOGIC ---
def run_crew_with_fallback():
    provider_chain = build_llm_chain()
    
    for provider_name, model_string, env_var_name in provider_chain:
        api_key = os.environ.get(env_var_name)
        
        if not api_key:
            logger.warning(f"⏩ SKIPPING '{provider_name}': Key not found in environment.")
            continue

        try:
            logger.info(f"🔄 ========== ATTEMPTING PROVIDER: {provider_name.upper()} ==========")
            llm = LLM(model=model_string, api_key=api_key)
            crew = build_crew(llm)
            
            # CrewAI execution
            result = crew.kickoff()
            result_str = str(result)
            
            # CHECK 1: Did CrewAI swallow the error and return it as the final article?
            if is_retryable(result_str):
                logger.warning(f"⚠️ CrewAI swallowed a rate-limit error on {provider_name.upper()}. Forcing fallback.")
                raise Exception(f"Swallowed API Error: {result_str}")
            
            # If we make it here, it's a genuine success
            logger.info(f"✅ ========== SUCCESS ON PROVIDER: {provider_name.upper()} ==========")
            return result_str

        except Exception as e:
            error_msg = str(e)
            # CHECK 2: Standard exception catching
            if is_retryable(error_msg):
                logger.warning(f"⚠️ {provider_name.upper()} hit a retryable block. Moving to next provider...")
                continue
            else:
                logger.error(f"❌ Non-retryable error on {provider_name.upper()}: {e}")
                raise e
                
    raise RuntimeError("🚨 CRITICAL: All LLM providers exhausted or failed.")

# --- EXECUTION ---
if __name__ == "__main__":
    result_text = run_crew_with_fallback()
    
    # Save logic
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"content/posts/{timestamp}-article.md"
    os.makedirs("content/posts", exist_ok=True)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(result_text)
        
    logger.info(f"💾 Article successfully saved to: {filename}")
