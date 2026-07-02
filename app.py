import os
import json
import re
import logging
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ─── LLM FALLBACK CHAIN ──────────────────────────────
# NOTE: LLM(fallbacks=[...]) does NOT catch Gemini's 503 UNAVAILABLE or
# 429 RESOURCE_EXHAUSTED errors — both were observed crashing crew.kickoff()
# instead of retrying. The fallback is now enforced manually below.

def build_llm_chain():
    return [
        LLM(model="gemini/gemini-2.5-flash-lite", api_key=os.environ.get("GEMINI_API_KEY")),
        LLM(model="groq/llama-3.3-70b-versatile", api_key=os.environ.get("GROQ_API_KEY")),
        LLM(model="openrouter/meta-llama/llama-3.3-70b-instruct", api_key=os.environ.get("OPENROUTER_API_KEY")),
    ]

RETRYABLE_MARKERS = ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "503", "429", "overloaded", "quota")

def is_retryable(exc: Exception) -> bool:
    msg = str(exc)
    return any(marker in msg for marker in RETRYABLE_MARKERS)

# Load match data passed from n8n via GitHub Dispatch
match_data_raw = os.environ.get("MATCH_DATA", "{}")
match_data = json.loads(match_data_raw)


# ─── AGENT + TASK FACTORY ────────────────────────────
# Rebuilt per-attempt so each provider attempt gets agents bound to that
# attempt's LLM. Cheap to construct — no API calls happen until kickoff().

def build_crew(llm):
    data_scout = Agent(
        role="Lead Cricket Performance Analyst",
        goal="Isolate high-leverage data anomalies within raw scorecard structures",
        backstory=(
            "20-year veteran data scientist specializing in cricket metrics. "
            "You ignore raw aggregates like total runs. You isolate situational "
            "impact values: dot-ball percentages under pressure, boundary response "
            "rates against specific bowling angles, momentum shifts over by over."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    chief_editor = Agent(
        role="Senior Editorial Director - DeathOvers",
        goal="Synthesize statistical briefs into elite, long-form sports journalism",
        backstory="""
You are the Chief Editor of DeathOvers, a cricket journalism platform built to
compete directly with Cricbuzz and ESPNcricinfo on editorial quality. You've
edited match reports for a decade and can spot a lazy scorecard summary in one line.

# Objective
Transform the data_scout's brief into a publish-ready article where the key
stat is reframed as insight — comparison, pattern, or stakes — never left as
a flat summary.

# Context
DeathOvers' growth depends on SEO-indexable, high-quality articles that readers
and Google both trust. Generic stat-dumps get ignored by both. Cricbuzz-caliber
headlines get clicked and ranked. Every article is a test: would a Cricbuzz
editor run this, or send it back?

# Method
For the key tactical moment identified in the brief, choose ONE lens to lead
with, in this priority order — use the first one the brief actually supports,
skip ones it doesn't:
1. Pattern — this is the Nth time this has happened (only if the brief states
   prior instances — count them, don't estimate)
2. Comparison — vs. this player/team's numbers elsewhere in the brief (only if
   present)
3. Cause → Effect — why it happened per the brief, and what it directly changed
4. Stakes — what this means going forward, ONLY if stated in the brief (e.g.
   "must-win game"). Never infer tournament implications or narratives not
   present in the data.

Headline test: read it back. If it's just a number and an outcome, rewrite it.
Opening-paragraph test: the first sentence must carry the chosen lens, not a
bare stat.

# Worked Example
BAD headline: "Player X scores 45 off 30 balls"
GOOD headline: "Player X finally breaks a four-innings strike-rate slump"
BAD opening: "Player X scored 45 runs off 30 balls today, helping his team
post a competitive total."
GOOD opening: "Player X hadn't struck above 105 in his last four innings —
today's 150 strike rate snapped that run cold."

No clichés. No invented stats or quotes. Only use data provided to you.
""",
        llm=llm,
        verbose=True,
        allow_delegation=False
    )

    scouting_task = Task(
        description=f"""
        Analyze this match data and produce a tight, data-backed brief:

        {json.dumps(match_data, indent=2)}

        Identify the ONE key tactical moment or pattern that decided this match.
        Output only facts and numbers. No prose, no flowery language.
        """,
        expected_output="A factual data brief, 100-150 words, highlighting the key tactical insight.",
        agent=data_scout
    )

    editorial_task = Task(
        description="""
        Take the data brief from the previous task and write a full article.

        Requirements:
        - 300-350 words
        - Headline and opening paragraph must apply the insight-over-summary filter
          from your backstory (Pattern / Comparison / Cause-Effect / Stakes, in
          that priority order) — never lead with a bare stat
        - Opening paragraph: 2-3 sentences max, first sentence carries the lens
        - Use ONLY data provided, never invent stats or quotes
        - No jargon, no clichés like "clinical performance"
        - End with a Match Facts section

        Output the article with this EXACT frontmatter block at the top:

        ---
        title: "[headline here]"
        date: "{date}"
        category: "[press-box OR tactical-sheets OR simulations]"
        targetEntity: "[team names]"
        metricFocus: "[the key metric analyzed]"
        confidenceScore: [number 0-100]
        ---

        [article body here]
        """.format(date=datetime.now().strftime("%Y-%m-%d")),
        expected_output="A complete markdown article with frontmatter, 300-350 words, headline and opening led by insight not summary.",
        agent=chief_editor,
        context=[scouting_task]
    )

    return Crew(
        agents=[data_scout, chief_editor],
        tasks=[scouting_task, editorial_task],
        verbose=True
    )


# ─── RUN WITH FALLBACK ───────────────────────────────

def run_crew_with_fallback():
    llm_chain = build_llm_chain()
    last_exception = None

    for i, llm in enumerate(llm_chain):
        provider_name = llm.model.split("/")[0]
        try:
            logger.info(f"[fallback-chain] Attempt {i+1}/{len(llm_chain)} using provider: {provider_name}")
            crew = build_crew(llm)
            result = crew.kickoff()
            logger.info(f"[fallback-chain] Success on provider: {provider_name}")
            return result
        except Exception as e:
            last_exception = e
            if is_retryable(e):
                logger.warning(f"[fallback-chain] '{provider_name}' failed retryably: {e}")
                continue
            else:
                logger.error(f"[fallback-chain] Non-retryable error on '{provider_name}': {e}")
                raise

    raise RuntimeError(f"All providers in fallback chain exhausted. Last error: {last_exception}")


result = run_crew_with_fallback()

# ─── SAVE ARTICLE TO FILE ───────────────────────────
article_text = str(result)

# Extract title from frontmatter for filename
title_match = re.search(r'title:\s*"([^"]+)"', article_text)
slug = "untitled-article"
if title_match:
    slug = title_match.group(1).lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')[:60]

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
filename = f"src/content/posts/{timestamp}-{slug}.md"

os.makedirs("src/content/posts", exist_ok=True)
with open(filename, "w", encoding="utf-8") as f:
    f.write(article_text)

print(f"Article saved: {filename}")
