"""
Epic 1 - Task: Run the parser across the ENTIRE Cricsheet corpus (22,284
matches) and write out one internal-schema JSON file per match.

Output layout:
  output/events/<match_id>.json   -> {"match_id", "meta", "events": [...]}

This is a one-time (well, re-run-on-refresh) batch job. The Replay Engine
and everything above it reads from output/events/, never from raw_data/.
"""
import json
import os
import time
from cricsheet_parser import parse_match

# intelligence/parser/batch_parse.py -> intelligence/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "raw_data")
MANIFEST = os.path.join(BASE_DIR, "output", "manifest.json")
EVENTS_DIR = os.path.join(BASE_DIR, "output", "events")

os.makedirs(EVENTS_DIR, exist_ok=True)

with open(MANIFEST) as f:
    manifest = json.load(f)

print(f"Parsing {len(manifest)} matches...")

start = time.time()
ok, failed = 0, []

for i, m in enumerate(manifest, 1):
    match_id = m["match_id"]
    src = os.path.join(RAW_DIR, f"{match_id}.json")
    dst = os.path.join(EVENTS_DIR, f"{match_id}.json")

    if not os.path.exists(src):
        failed.append((match_id, "raw file missing"))
        continue

    try:
        parsed = parse_match(src)
        # carry manifest tags forward onto meta for convenience
        parsed["meta"]["competition_code"] = m["competition_code"]
        parsed["meta"]["team_type"] = m["team_type"]
        parsed["meta"]["is_limited_overs"] = m["is_limited_overs"]

        with open(dst, "w", encoding="utf-8") as out:
            json.dump(parsed, out)
        ok += 1
    except Exception as e:
        failed.append((match_id, str(e)))

    if i % 2000 == 0:
        elapsed = time.time() - start
        print(f"  {i}/{len(manifest)} done ({elapsed:.0f}s elapsed)")

elapsed = time.time() - start
print(f"\nDone in {elapsed:.0f}s")
print(f"Parsed OK: {ok}")
print(f"Failed: {len(failed)}")
if failed:
    print("First 20 failures:")
    for fid, err in failed[:20]:
        print(f"  {fid}: {err}")

with open(os.path.join(BASE_DIR, "output", "parse_failures.json"), "w") as f:
    json.dump(failed, f, indent=2)
