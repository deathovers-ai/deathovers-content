"""
Epic 1 - Task: Build dataset manifest from Cricsheet README.txt
Full corpus - all formats, all competitions. Downstream engines (Insight
Engine etc.) will scope themselves to limited-overs formats; the manifest
and parser stay format-agnostic so nothing has to be re-parsed later.
"""
import re
import json
import os

# intelligence/parser/build_manifest.py -> intelligence/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(BASE_DIR, "raw_data", "README.txt")
OUT_DIR = os.path.join(BASE_DIR, "output")
OUT = os.path.join(OUT_DIR, "manifest.json")

os.makedirs(OUT_DIR, exist_ok=True)

# Formats considered "limited-overs" for downstream Insight Engine tagging.
# Kept here so the manifest can flag scope without the parser needing to care.
LIMITED_OVERS_CODES = {
    "T20", "IT20", "IPL", "ODI", "ODM", "NTB", "CCH", "RLC", "SMA", "BBL",
    "WBB", "BPL", "SSM", "CPL", "PSL", "PKS", "HND", "CTC", "SSH", "RHF",
    "MLT", "ILT", "SAT", "CEC", "LPL", "MCL", "ODC", "IPT", "WTB", "WOD",
    "MLC", "WSL", "WPL", "IPO", "MCT", "NPL", "MSL", "BWT", "FRB", "MDM",
}

line_re = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) - (international|club) - (\S+) - (male|female) - (\d+) - (.+)$"
)

manifest = []
with open(README, encoding="utf-8") as f:
    for line in f:
        m = line_re.match(line.strip())
        if not m:
            continue
        date, team_type, comp_code, gender, match_id, teams = m.groups()
        manifest.append({
            "match_id": match_id,
            "date": date,
            "team_type": team_type,
            "competition_code": comp_code,
            "gender": gender,
            "teams": teams,
            "is_limited_overs": comp_code in LIMITED_OVERS_CODES or comp_code != "Test",
        })

print(f"Total matches in manifest: {len(manifest)}")
from collections import Counter
print(Counter(m["competition_code"] for m in manifest).most_common(10))
print(Counter(m["gender"] for m in manifest))
print("Limited-overs matches:", sum(1 for m in manifest if m["is_limited_overs"]))
print("Test matches:", sum(1 for m in manifest if not m["is_limited_overs"]))

with open(OUT, "w") as f:
    json.dump(manifest, f, indent=2)
print(f"Saved to {OUT}")
