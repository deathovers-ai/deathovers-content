import json
from insight_engine_fixed import InsightEngine, _overs_to_balls, _cricket_over_to_decimal

_engine = InsightEngine()

def get_insights_tab_data(context: dict) -> dict:
    """
    Returns exactly what the frontend Insights Tab needs.
    """
    raw = _engine.generate_all(context)
    
    debug_log = []
    checks = [
        ("venue_pregame", ["venue_key", "match_type"]),
        ("venue_score", ["venue_key","match_type","current_score","current_wickets","overs_completed_str"]),
        ("venue_phase", ["venue_key","match_type","phase_name","current_phase_runs","current_phase_balls"]),
        ("player_form", ["player_name","player_current_runs","player_current_balls"]),
        ("situation", ["recent_balls","innings_avg_run_rate","innings_avg_strike_rate","partnership_runs","partnership_balls"]),
        ("projection", ["venue_key","match_type","current_score","current_over_decimal","current_wickets"]),
        ("chase", ["venue_key","match_type","current_score","target","current_over_decimal","balls_remaining"]),
    ]
    for name, keys in checks:
        missing = [k for k in keys if k not in context or context[k] is None]
        if missing:
            debug_log.append(f"{name}: missing keys {missing}")
        else:
            debug_log.append(f"{name}: keys OK")
    
    return {
        "tab_visible": True,
        "insights": raw,
        "count": len(raw),
        "_debug": debug_log,
    }
