"""
Epic 4b (revised) - Registry-based player identity verification.

IMPORTANT CORRECTION to the earlier approach: the initials-pattern merge
candidates (merge_candidates.json) were built by GUESSING from name string
similarity ("R Sharma" looks like it could be short for "RG Sharma").
That guessing turned out to be unreliable - see below.

Cricsheet actually ships a `registry.people` block in every match file,
mapping each name-as-recorded to a stable player ID (drawn from ESPN
Cricinfo's player database). This is REAL ground truth, not a guess.

We checked our top "high confidence" name-pattern candidates against this
registry across the full 22,309-match corpus, and NONE of them share a
registry ID:
    R Sharma vs RG Sharma       -> different IDs
    S Williams vs SC Williams   -> different IDs
    S Smith vs SPD Smith        -> different IDs
    J Anderson vs JM Anderson   -> different IDs
    J Broad vs SCJ Broad        -> different IDs
    G Johnson vs MG Johnson     -> different IDs

This means Cricsheet's own player database does NOT consider these the
same person (or at minimum, never had enough info to link them - which
is itself a meaningful signal not to merge blindly). Our earlier
name-pattern guesses should NOT be trusted or used to build
player_aliases.json.

This module replaces that approach with the real thing:
1. Build name -> registry_id mapping across the full corpus (ground truth)
2. Build registry_id -> {all names that ID was ever recorded as} (this IS
   safe to merge on - if Cricsheet's own database says two name strings
   share an ID, they are confirmed the same real player)
3. Output only registry-confirmed merges to player_aliases.json - no
   human guessing required for these, because Cricsheet already did the
   identity resolution correctly.
4. Separately, report names with NO registry coverage (older/lower-profile
   matches often lack the registry block) - these remain un-mergeable
   without human review, honestly labeled as such.
"""
import json
import os
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "raw_data")
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
ALIASES_FILE = os.path.join(CONTEXT_DIR, "player_aliases.json")
REGISTRY_REPORT_FILE = os.path.join(CONTEXT_DIR, "registry_coverage_report.json")


def build_registry_maps():
    """
    Scan all raw Cricsheet files for the registry.people block.
    Returns:
      name_to_ids: {name_string: set(player_ids)}
      id_to_names: {player_id: set(name_strings)}
    """
    name_to_ids = defaultdict(set)
    id_to_names = defaultdict(set)

    files = [f for f in os.listdir(RAW_DIR) if f.endswith(".json")]
    print(f"Scanning {len(files)} raw match files for registry.people data...")

    processed = 0
    with_registry = 0
    for fname in files:
        path = os.path.join(RAW_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue

        registry = d.get("info", {}).get("registry", {}).get("people", {})
        if registry:
            with_registry += 1
        for name, pid in registry.items():
            name_to_ids[name].add(pid)
            id_to_names[pid].add(name)

        processed += 1
        if processed % 5000 == 0:
            print(f"  {processed}/{len(files)}")

    print(f"Done. {with_registry}/{len(files)} matches had registry data. "
          f"{len(name_to_ids)} distinct names resolved to {len(id_to_names)} distinct player IDs.")
    return dict(name_to_ids), dict(id_to_names)


def build_confirmed_aliases(id_to_names):
    """
    For every player ID that maps to MORE than one name string, that's a
    confirmed same-person merge (Cricsheet's own registry says so - not
    a guess). Pick the longest/most-specific name as canonical, alias
    the rest to it.
    """
    aliases = {}
    confirmed_groups = []
    for pid, names in id_to_names.items():
        if len(names) < 2:
            continue
        names_sorted = sorted(names, key=len, reverse=True)
        canonical = names_sorted[0]
        variants = names_sorted[1:]
        for v in variants:
            aliases[v] = canonical
        confirmed_groups.append({"canonical": canonical, "variants": variants, "player_id": pid})

    return aliases, confirmed_groups


def check_unregistered_names(name_to_ids, player_stats_file):
    """
    Cross-reference against the full player_stats.json (which has ALL
    names seen in events, including those from matches with no registry
    block) to see how many names have zero registry coverage - these
    can't be verified this way and need a different approach if they're
    worth merging.
    """
    if not os.path.exists(player_stats_file):
        return None
    with open(player_stats_file, encoding="utf-8") as f:
        all_names = set(json.load(f).keys())

    covered = set(name_to_ids.keys())
    uncovered = all_names - covered
    return {
        "total_names": len(all_names),
        "registry_covered": len(covered & all_names),
        "no_registry_data": len(uncovered),
        "sample_uncovered": sorted(uncovered)[:30],
    }


if __name__ == "__main__":
    name_to_ids, id_to_names = build_registry_maps()

    print("\nBuilding registry-CONFIRMED aliases (real ground truth, not guessing)...")
    aliases, confirmed_groups = build_confirmed_aliases(id_to_names)
    print(f"Found {len(confirmed_groups)} player IDs with multiple recorded name variants "
          f"({len(aliases)} total alias entries).")

    os.makedirs(CONTEXT_DIR, exist_ok=True)
    with open(ALIASES_FILE, "w", encoding="utf-8") as f:
        json.dump(aliases, f, indent=2)
    print(f"Saved confirmed aliases to {ALIASES_FILE}")
    print("(This file is now safe to use directly with player_context.py - "
          "no manual review needed, these merges are Cricsheet-verified.)")

    print("\nSample confirmed merges:")
    for g in confirmed_groups[:15]:
        print(f"  {g['canonical']}  <-  {g['variants']}  (id: {g['player_id']})")

    player_stats_file = os.path.join(CONTEXT_DIR, "player_stats.json")
    coverage = check_unregistered_names(name_to_ids, player_stats_file)
    if coverage:
        with open(REGISTRY_REPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(coverage, f, indent=2)
        print(f"\nRegistry coverage report saved to {REGISTRY_REPORT_FILE}")
        print(f"  {coverage['registry_covered']}/{coverage['total_names']} names have registry IDs")
        print(f"  {coverage['no_registry_data']} names have NO registry data "
              f"(cannot be auto-verified this way)")

    # Specifically re-check our earlier "confident" guesses against real data
    print("\n--- Re-checking earlier name-pattern guesses against real registry ---")
    test_pairs = [
        ("R Sharma", "RG Sharma"), ("P Nissanka", "RAP Nissanka"),
        ("S Williams", "SC Williams"), ("S Smith", "SPD Smith"),
        ("J Anderson", "JM Anderson"), ("J Broad", "SCJ Broad"),
    ]
    for a, b in test_pairs:
        ia, ib = name_to_ids.get(a, set()), name_to_ids.get(b, set())
        shared = ia & ib
        verdict = "CONFIRMED SAME PERSON" if shared else "NOT confirmed - do not merge on this basis"
        print(f"  {a} vs {b}: {verdict}")
