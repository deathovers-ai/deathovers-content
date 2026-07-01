import os
import json
import re
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
import google.generativeai as genai

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# ─── LLM CONFIGURATION ───────────────────────────────
gemini_llm = LLM(
    model="gemini/gemini-2.5-flash-lite",
    api_key=os.environ.get("GEMINI_API_KEY")
)

# Load match data passed from n8n via GitHub Dispatch
match_data_raw = os.environ.get("MATCH_DATA", "{}")
match_data = json.loads(match_data_raw)

# ─── AGENT DEFINITIONS ───────────────────────────────
data_scout = Agent(
    role="Lead Cricket Performance Analyst",
    goal="Isolate high-leverage data anomalies within raw scorecard structures",
    backstory=(
        "20-year veteran data scientist specializing in cricket metrics. "
        "You ignore raw aggregates like total runs. You isolate situational "
        "impact values: dot-ball percentages under pressure, boundary response "
        "rates against specific bowling angles, momentum shifts over by over."
    ),
    llm=gemini_llm,
    verbose=True,
    allow_delegation=False
)

chief_editor = Agent(
    role="Senior Editorial Director - DeathOvers",
    goal="Synthesize statistical briefs into elite, long-form sports journalism",
    backstory=(
        "Legendary cricket journalist with the narrative prose of Gideon Haigh "
        "and the sharp tactical eye of an international captain. You write "
        "high-impact, analytical content. No clichés. No invented stats. "
        "Only use data provided to you."
    ),
    llm=gemini_llm,
    verbose=True,
    allow_delegation=False
)

# ─── TASK DEFINITIONS ───────────────────────────────
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
    - Punchy, factual headline
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
    expected_output="A complete markdown article with frontmatter, 300-350 words.",
    agent=chief_editor,
    context=[scouting_task]
)

# ─── RUN CREW ───────────────────────────────────────
crew = Crew(
    agents=[data_scout, chief_editor],
    tasks=[scouting_task, editorial_task],
    verbose=True
)

result = crew.kickoff()

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
