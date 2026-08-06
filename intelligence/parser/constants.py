"""
Shared limited-overs phase boundaries.

Single source of truth for powerplay / middle / death windows.
Import from here — do not re-declare these overs elsewhere.

F11: ODI kept; The Hundred + T10 added. T10 is experimental
(league PP rules vary); The Hundred PP is the official first 25 balls.
"""

# Over windows are half-open [start, end) in 0-indexed overs.
# HUNDRED assumes Cricsheet-style 5-ball overs (20 overs × 5 = 100 balls).
PHASE_BOUNDARIES = {
    "T20_LIKE": {"powerplay": (0, 6), "middle": (6, 15), "death": (15, 20)},
    "ODI_LIKE": {"powerplay": (0, 10), "middle": (10, 40), "death": (40, 50)},
    # Official PP = first 25 balls → first 5 five-ball overs. Death = last 25 balls.
    "HUNDRED": {"powerplay": (0, 5), "middle": (5, 15), "death": (15, 20)},
    # ponytail: T10 fielding restrictions differ by league; 0-3 / 3-7 / 7-10 is
    # an analytic default until we ingest league-specific rules (upgrade: per-comp override).
    "T10_LIKE": {"powerplay": (0, 3), "middle": (3, 7), "death": (7, 10)},
}

EXPERIMENTAL_PHASE_KINDS = frozenset({"T10_LIKE"})

BALLS_PER_OVER = {
    "T20_LIKE": 6,
    "ODI_LIKE": 6,
    "T10_LIKE": 6,
    "HUNDRED": 5,
}

INNINGS_LEGAL_BALLS = {
    "T20_LIKE": 120,
    "ODI_LIKE": 300,
    "T10_LIKE": 60,
    "HUNDRED": 100,
}

# Competition / match-type codes → phase kind.
# HND = Cricsheet The Hundred. HUNDRED/100/THE_HUNDRED = live feed aliases.
_FORMAT_TO_KIND = {
    "ODI": "ODI_LIKE",
    "ODM": "ODI_LIKE",
    "T10": "T10_LIKE",
    "HND": "HUNDRED",
    "HUNDRED": "HUNDRED",
    "100": "HUNDRED",
    "THE_HUNDRED": "HUNDRED",
}

ODI_LIKE_FORMATS = frozenset({"ODI", "ODM"})
HUNDRED_FORMATS = frozenset({"HND", "HUNDRED", "100", "THE_HUNDRED"})
T10_FORMATS = frozenset({"T10"})


def normalize_match_type(match_type: str | None) -> str:
    """Uppercase competition / feed format code (empty → '')."""
    return (match_type or "").strip().upper()


def phase_kind_for_match_type(match_type: str) -> str:
    """Return phase-kind key for a competition / match type code."""
    code = normalize_match_type(match_type)
    if code in _FORMAT_TO_KIND:
        return _FORMAT_TO_KIND[code]
    return "T20_LIKE"


def phase_set_for_match_type(match_type: str) -> dict:
    """Return {phase_name: (start_over, end_over)} for a match type."""
    return PHASE_BOUNDARIES[phase_kind_for_match_type(match_type)]


def phase_set_for_total_overs(total_overs: int | float, match_type: str | None = None) -> dict:
    """
    Return phase windows from innings length (context-build path).
    Prefer match_type when known — total overs alone cannot distinguish
    T20 (6-ball × 20) from The Hundred (5-ball × 20).
    """
    if match_type:
        return phase_set_for_match_type(match_type)
    if total_overs <= 10:
        return PHASE_BOUNDARIES["T10_LIKE"]
    if total_overs > 20:
        return PHASE_BOUNDARIES["ODI_LIKE"]
    return PHASE_BOUNDARIES["T20_LIKE"]


def phase_bounds_list(match_type: str) -> list[tuple[str, int, int]]:
    """[(name, start_over, end_over), ...] in innings order."""
    phases = phase_set_for_match_type(match_type)
    return [(name, start, end) for name, (start, end) in phases.items()]


def determine_phase_from_over(over_number, match_type: str) -> str:
    """Map a 0-indexed over number into powerplay / middle / death."""
    for name, start, end in phase_bounds_list(match_type):
        if start <= over_number < end:
            return name
    return "death"


def balls_per_over_for_match_type(match_type: str) -> int:
    return BALLS_PER_OVER[phase_kind_for_match_type(match_type)]


def innings_legal_balls(match_type: str) -> int:
    return INNINGS_LEGAL_BALLS[phase_kind_for_match_type(match_type)]


def is_experimental_format(match_type: str) -> bool:
    return phase_kind_for_match_type(match_type) in EXPERIMENTAL_PHASE_KINDS


def format_total_overs(match_type: str) -> int:
    """Scheduled overs for context builds (Hundred counted as 20 five-ball overs)."""
    kind = phase_kind_for_match_type(match_type)
    if kind == "ODI_LIKE":
        return 50
    if kind == "T10_LIKE":
        return 10
    if kind == "HUNDRED":
        return 20
    return 20
