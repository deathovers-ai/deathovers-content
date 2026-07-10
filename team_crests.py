"""
Team name -> Cricbuzz imageId lookup, sourced from Cricbuzz's public
/cricket-team/ list (team master data, not live-score quota). Used to
attach crest imageIds onto carousel match objects without any extra
API call per request.

CricketData.org's `teams` array gives free-text names like "India",
"West Indies Women", "Shivamogga Yodhas" -- full names, franchise/
domestic teams, and women's teams included, which don't map 1:1 onto
Cricbuzz's international team list. TEAM_NAME_TO_IMAGE_ID only covers
the ~40 full-member/associate teams from that list; anything else
(franchise T20 teams, domestic sides, women's teams) intentionally
falls through to the frontend's 2-letter fallback badge rather than
guessing at a wrong crest.
"""

TEAM_NAME_TO_IMAGE_ID: dict[str, int] = {
    "India": 776162,
    "Afghanistan": 776177,
    "Ireland": 839366,
    "Pakistan": 776308,
    "Australia": 776202,
    "Sri Lanka": 776254,
    "Bangladesh": 776210,
    "England": 776237,
    "West Indies": 776191,
    "South Africa": 776287,
    "Zimbabwe": 776198,
    "New Zealand": 776333,
    "Malaysia": 776319,
    "Nepal": 776331,
    "Germany": 776260,
    "Namibia": 776326,
    "Denmark": 776232,
    "Singapore": 776275,
    "Papua New Guinea": 776304,
    "Kuwait": 776312,
    "Vanuatu": 776229,
    "Jersey": 776300,
    "Oman": 776328,
    "Fiji": 776251,
    "Italy": 776295,
    "Botswana": 776225,
    "Belgium": 776219,
    "Iran": 776282,
    "Uganda": 776233,
    "United Arab Emirates": 776242,
    "Hong Kong, China": 776271,
    "Kenya": 776303,
    "United States of America": 776186,
    "Scotland": 776280,
    "Netherlands": 776335,
    "Bermuda": 776221,
    "Canada": 776227,
    "Uzbekistan": 1011873,
}


def crest_image_id(team_name: str) -> "int | None":
    """
    Look up a Cricbuzz crest imageId for a free-text team name coming
    out of CricketData.org. Handles the common "X Women" suffix by
    trying the bare name too, since women's national sides share the
    same crest as the men's team on Cricbuzz. Returns None (not a
    fallback id) for anything unmapped -- the frontend handles that
    with its own 2-letter badge, which is safer than silently showing
    the wrong flag.
    """
    if not team_name:
        return None
    name = team_name.strip()
    if name in TEAM_NAME_TO_IMAGE_ID:
        return TEAM_NAME_TO_IMAGE_ID[name]
    if name.endswith(" Women"):
        bare = name[: -len(" Women")].strip()
        if bare in TEAM_NAME_TO_IMAGE_ID:
            return TEAM_NAME_TO_IMAGE_ID[bare]
    return None
