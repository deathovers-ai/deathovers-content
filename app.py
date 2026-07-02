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
