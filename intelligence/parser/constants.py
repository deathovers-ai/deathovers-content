"""
Shared limited-overs phase boundaries.

Single source of truth for powerplay / middle / death windows.
Import from here — do not re-declare these overs elsewhere.

F11:
  - T20 / ODI / T10 stay **over-based** (6-ball overs; T10 experimental).
  - The Hundred is **ball-native** (ECB: 100 balls, 25-ball powerplay).
    Cricsheet 5-ball "overs" are an adapter only — never treat Hundred as T20.
"""

# ---------------------------------------------------------------------------
# Over-based kinds (6-ball). HUNDRED is intentionally NOT in this table.
# ---------------------------------------------------------------------------
PHASE_BOUNDARIES = {
    "T20_LIKE": {"powerplay": (0, 6), "middle": (6, 15), "death": (15, 20)},
    "ODI_LIKE": {"powerplay": (0, 10), "middle": (10, 40), "death": (40, 50)},
    # ponytail: T10 fielding restrictions differ by league; 0-3 / 3-7 / 7-10 is
    # an analytic default until we ingest league-specific rules (upgrade: per-comp override).
    "T10_LIKE": {"powerplay": (0, 3), "middle": (3, 7), "death": (7, 10)},
}

# Ball-native (ECB / The Hundred FAQ). Official PP = first 25 balls.
# Middle/death after PP are analytic (rules only define the powerplay).
PHASE_BOUNDARIES_BALLS = {
    "HUNDRED": {"powerplay": (0, 25), "middle": (25, 75), "death": (75, 100)},
}

EXPERIMENTAL_PHASE_KINDS = frozenset({"T10_LIKE"})
BALL_NATIVE_KINDS = frozenset({"HUNDRED"})

BALLS_PER_OVER = {
    "T20_LIKE": 6,
    "ODI_LIKE": 6,
    "T10_LIKE": 6,
    # Cricsheet storage only — product phases use PHASE_BOUNDARIES_BALLS.
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


def is_ball_native_format(match_type: str) -> bool:
    return phase_kind_for_match_type(match_type) in BALL_NATIVE_KINDS


def _hundred_cricsheet_over_windows() -> dict:
    """
    Adapter for Cricsheet event['over'] scans only (5-ball overs).
    Derived from ball windows — do not treat as the rulebook.
    """
    bpo = BALLS_PER_OVER["HUNDRED"]
    return {
        name: (start // bpo, end // bpo)
        for name, (start, end) in PHASE_BOUNDARIES_BALLS["HUNDRED"].items()
    }


def phase_set_for_match_type(match_type: str) -> dict:
    """
    Return {phase_name: (start, end)} for venue/event over-index scans.

    For Hundred this is the Cricsheet 5-ball-over adapter. Prefer
    phase_bounds_balls() / determine_phase_from_balls() for live logic.
    """
    kind = phase_kind_for_match_type(match_type)
    if kind == "HUNDRED":
        return _hundred_cricsheet_over_windows()
    return PHASE_BOUNDARIES[kind]


def phase_bounds_balls(match_type: str) -> list[tuple[str, int, int]]:
    """
    [(name, start_ball, end_ball), ...] half-open.
    Over-based formats are converted via balls_per_over (T20/ODI/T10 unchanged).
    """
    kind = phase_kind_for_match_type(match_type)
    if kind in PHASE_BOUNDARIES_BALLS:
        phases = PHASE_BOUNDARIES_BALLS[kind]
        return [(name, start, end) for name, (start, end) in phases.items()]
    bpo = BALLS_PER_OVER[kind]
    return [
        (name, start * bpo, end * bpo)
        for name, (start, end) in PHASE_BOUNDARIES[kind].items()
    ]


def phase_set_for_total_overs(total_overs: int | float, match_type: str | None = None) -> dict:
    """
    Return phase windows from innings length (context-build path).

    Prefer match_type when known. Without match_type, never infer Hundred:
    20 overs alone means T20 (6-ball), not 100-ball cricket.
    """
    if match_type:
        return phase_set_for_match_type(match_type)
    if total_overs <= 10:
        return PHASE_BOUNDARIES["T10_LIKE"]
    if total_overs > 20:
        return PHASE_BOUNDARIES["ODI_LIKE"]
    return PHASE_BOUNDARIES["T20_LIKE"]


def phase_bounds_list(match_type: str) -> list[tuple[str, int, int]]:
    """[(name, start_over, end_over), ...] for over-index consumers."""
    phases = phase_set_for_match_type(match_type)
    return [(name, start, end) for name, (start, end) in phases.items()]


def overs_to_legal_balls(overs, match_type: str) -> int:
    """Convert overs (e.g. 6.3) to legal balls using format balls-per-over."""
    bpo = balls_per_over_for_match_type(match_type)
    try:
        overs_f = float(overs)
    except (TypeError, ValueError):
        return 0
    whole = int(overs_f)
    balls_in_over = int(round((overs_f - whole) * 10))
    if balls_in_over > bpo:
        balls_in_over = bpo
    return max(0, whole * bpo + balls_in_over)


def determine_phase_from_balls(legal_balls_bowled, match_type: str) -> str:
    """Map legal balls bowled (0-indexed count) into powerplay / middle / death."""
    try:
        balls = float(legal_balls_bowled)
    except (TypeError, ValueError):
        balls = 0.0
    for name, start, end in phase_bounds_balls(match_type):
        if start <= balls < end:
            return name
    return "death"


def determine_phase_from_over(over_number, match_type: str) -> str:
    """
    Map a 0-indexed over number into powerplay / middle / death.

    Hundred: treat overs as Cricsheet 5-ball sets, convert to balls, then
    use ball-native windows (keeps T20/ODI on pure over windows).
    """
    if is_ball_native_format(match_type):
        return determine_phase_from_balls(
            overs_to_legal_balls(over_number, match_type), match_type
        )
    try:
        over_f = float(over_number)
    except (TypeError, ValueError):
        over_f = 0.0
    for name, start, end in phase_bounds_list(match_type):
        if start <= over_f < end:
            return name
    return "death"


def balls_per_over_for_match_type(match_type: str) -> int:
    return BALLS_PER_OVER[phase_kind_for_match_type(match_type)]


def innings_legal_balls(match_type: str) -> int:
    return INNINGS_LEGAL_BALLS[phase_kind_for_match_type(match_type)]


def is_experimental_format(match_type: str) -> bool:
    return phase_kind_for_match_type(match_type) in EXPERIMENTAL_PHASE_KINDS


def format_total_overs(match_type: str) -> int:
    """Scheduled overs for context builds (Hundred = 20 five-ball Cricsheet overs)."""
    kind = phase_kind_for_match_type(match_type)
    if kind == "ODI_LIKE":
        return 50
    if kind == "T10_LIKE":
        return 10
    if kind == "HUNDRED":
        return 20
    return 20
