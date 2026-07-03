import os
import sys
import json
from crewai import Agent, Task, Crew, Process, LLM

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
    Updated to use CrewAI's native LLM class.
    Capped at 1500 tokens to prevent OpenRouter 402 errors.
    """
    # 1. Primary Model: Gemini (via OpenRouter)
    try:
        return LLM(
            model="openrouter/google/gemini-2.5-pro", 
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            max_tokens=1500
        )
    except Exception:
        pass

    # 2. Secondary Model: Groq (Llama 3.3 70B via OpenRouter)
    try:
        return LLM(
            model="openrouter/meta-llama/llama-3.3-70b-instruct",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            max_tokens=1500
        )
    except Exception:
        pass

    # 3. Final Failover: General OpenRouter Provider
    return LLM(
        model="openrouter/auto",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        max_tokens=1500
    )

def main():
    # Load raw text payload sent by n8n
    try:
        raw_payload = os.getenv("MATCH_DATA_PAYLOAD", "{}")
        match_data = json.loads(raw_payload)
    except Exception as e:
        print(f"Error parsing match payload JSON: {e}")
        sys.exit(1)

    # Initialize the resilient native LLM engine
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
        backstory="""You are the lead editor for DeathOvers. Your writing style
