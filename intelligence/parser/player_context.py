"""
Epic 4b - Context Repository (Player layer)

IMPORTANT DESIGN NOTE: player identity resolution across name variants
is handled via player_aliases.json (built by registry_verification.py
from Cricsheet's own verified player registry - NOT by guessing from
name string patterns). If player_aliases.json exists, this script
applies those confirmed merges. If it doesn't exist yet, stats are
built on raw names as-is (safe default, no merging).
"""
import json
import os
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_DIR = os.path.join(BASE_DIR, "output", "events")
MANIFEST = os.path.join(BASE_DIR, "output", "manifest.json")
CONTEXT_DIR = os.path.join(BASE_DIR, "output", "context")
PLAYER_STATS_FILE = os.path.join(CONTEXT_DIR, "player_stats.json")
ALIASES_FILE = os.path.join(CONTEXT_DIR, "player_aliases.json")

LIMITED_OVERS_FORMATS = {"T20", "IT20", "IPL", "ODI", "ODM"}


def load_aliases():
    if os.path.exists(ALIASES_FILE):
        with open(ALIASES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def
