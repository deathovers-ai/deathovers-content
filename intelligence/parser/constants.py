"""
Shared limited-overs phase boundaries.

Single source of truth for powerplay / middle / death windows.
Import from here — do not re-declare these overs elsewhere.
"""

# T20-like: PP 0-6, middle 6-15, death 15-20.
# ODI-like: PP 0-10, middle 10-40, death 40-50.
PHASE_BOUNDARIES = {
    "T20_LIKE": {"powerplay": (0, 6), "middle": (6, 15), "death": (15, 20)},
    "ODI_LIKE": {"powerplay": (0, 10), "middle": (10, 40), "death": (40, 50)},
}

ODI_LIKE_FORMATS = frozenset({"ODI", "ODM"})


def phase_kind_for_match_type(match_type: str) -> str:
    """Return 'ODI_LIKE' or 'T20_LIKE' for a competition / match type code."""
    return "ODI_LIKE" if match_type in ODI_LIKE_FORMATS else "T20_LIKE"


def phase_set_for_match_type(match_type: str) -> dict:
    """Return {phase_name: (start_over, end_over)} for a match type."""
    return PHASE_BOUNDARIES[phase_kind_for_match_type(match_type)]


def phase_set_for_total_overs(total_overs: int | float) -> dict:
    """Return phase windows from innings length (context-build path)."""
    return PHASE_BOUNDARIES["ODI_LIKE"] if total_overs > 20 else PHASE_BOUNDARIES["T20_LIKE"]


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
