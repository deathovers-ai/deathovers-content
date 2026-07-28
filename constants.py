"""Single source of truth for all cricket format definitions.
When formats change (IPL powerplay tweaks, new leagues), edit HERE only."""

PHASE_BOUNDARIES = {
    't20': {
        'powerplay': (0, 6),
        'middle': (6, 15),
        'death': (15, 20)
    },
    'odi': {
        'powerplay': (0, 10),
        'middle': (10, 40),
        'death': (40, 50)
    },
    't10': {
        'powerplay': (0, 2),
        'middle': (2, 5),
        'death': (5, 10)
    },
    'the_hundred': {
        'powerplay': (0, 25),      # 25 balls
        'middle': (25, 70),        # 45 balls
        'death': (70, 100)         # 30 balls
    }
}

SIGNIFICANCE_THRESHOLD = 0.10  # 10% minimum deviation

DATA_CONFIDENCE_CUTOFF = '2005-01-01'  # Pre-thin-coverage exclusion

MIN_VENUE_INNINGS = 5
MIN_PHASE_BALLS = 100
MIN_MATCHUP_BALLS = 30
