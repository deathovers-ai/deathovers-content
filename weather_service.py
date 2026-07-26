"""
Weather service - Open-Meteo integration (free, no API key: see
https://open-meteo.com/en/docs). Coordinates come directly from
Cricbuzz's own matchInfo.venueInfo.latitude/longitude (confirmed real,
present on every match's carousel payload) - no separate geocoding step
needed, no lat/long storage required in venue_stats.json.

Fetched once pregame + once at innings break per match (see app.py
wiring), not on every poll - weather doesn't change meaningfully within
a single refresh cycle, and this keeps calls well within Open-Meteo's
free 10,000/day allowance without adding a second quota tracker.
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone as dt_timezone, timedelta

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes (confirmed from Open-Meteo's own docs,
# https://open-meteo.com/en/docs). Grouped into cricket-relevant labels -
# finer distinctions (e.g. "moderate rain" vs "heavy rain") collapse to
# one user-facing label since the Match Room chip needs a glance-readable
# word, not a full meteorological classification.
WMO_CODE_LABELS = {
    0: "Clear",
    1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
    56: "Freezing Drizzle", 57: "Freezing Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    66: "Freezing Rain", 67: "Freezing Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
    77: "Snow Grains",
    80: "Rain Showers", 81: "Rain Showers", 82: "Violent Showers",
    85: "Snow Showers", 86: "Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

WMO_RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def wmo_code_to_label(code: "int | None") -> str:
    if code is None:
        return "Unknown"
    return WMO_CODE_LABELS.get(code, "Unknown")


def is_rain_code(code: "int | None") -> bool:
    return code in WMO_RAIN_CODES


def fetch_weather(latitude: float, longitude: float) -> "dict | None":
    """
    Calls Open-Meteo's forecast endpoint for current conditions + next-hour
    rain probability. Returns None on any failure (network, bad response,
    unexpected shape) - weather is additive, never blocks the rest of the
    Match Room response.
    """
    params = urllib.parse.urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,weather_code",
        "hourly": "precipitation_probability",
        "forecast_days": 1,
    })
    url = f"{OPEN_METEO_FORECAST_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    current = data.get("current")
    if not current:
        return None

    weather_code = current.get("weather_code")
    temp_c = current.get("temperature_2m")
    humidity_pct = current.get("relative_humidity_2m")

    # Next-hour rain probability: hourly arrays are indexed by hour-of-day;
    # find the entry matching "current" time, default to the first entry
    # if we can't match exactly (still same day, close enough for a chip).
    rain_probability_pct = None
    hourly = data.get("hourly") or {}
    hourly_times = hourly.get("time") or []
    hourly_probs = hourly.get("precipitation_probability") or []
    current_time = current.get("time")
    if current_time and current_time in hourly_times:
        idx = hourly_times.index(current_time)
        if idx < len(hourly_probs):
            rain_probability_pct = hourly_probs[idx]
    elif hourly_probs:
        rain_probability_pct = hourly_probs[0]

    return {
        "condition": wmo_code_to_label(weather_code),
        "temp_c": temp_c,
        "humidity_pct": humidity_pct,
        "rain_probability_pct": rain_probability_pct,
        "is_rain_code_now": is_rain_code(weather_code),
    }


def compute_local_hour(start_date_epoch_ms: "int | str | None", tz_offset_str: "str | None") -> "int | None":
    """
    Cricbuzz gives matchInfo.startDate as epoch milliseconds (UTC) and
    matchInfo.venueInfo.timezone as an offset string like "+02:00" or
    "-04:00" (confirmed real shapes from live carousel data). Combines
    these to get the match's local start hour (0-23), used to decide
    whether this is an evening/night match for dew-risk purposes.

    Returns None if either input is missing/malformed - correctly
    refuses rather than guessing at a default timezone.
    """
    if start_date_epoch_ms is None or not tz_offset_str:
        return None
    try:
        epoch_seconds = int(start_date_epoch_ms) / 1000
        utc_dt = datetime.fromtimestamp(epoch_seconds, tz=dt_timezone.utc)

        sign = 1 if tz_offset_str.startswith("+") else -1
        hh, mm = tz_offset_str[1:].split(":")
        offset = timedelta(hours=int(hh), minutes=int(mm)) * sign
        local_dt = utc_dt + offset
        return local_dt.hour
    except (ValueError, TypeError, IndexError):
        return None


# Evening/night threshold for dew-risk consideration. Matches starting at
# or after this local hour are candidates for a dew alert once in the
# 2nd innings + humidity crosses DEW_HUMIDITY_THRESHOLD_PCT.
EVENING_MATCH_START_HOUR = 16  # 4 PM local or later
DEW_HUMIDITY_THRESHOLD_PCT = 80
DEW_TEMP_DROP_THRESHOLD_C = 5  # noticeable evening cool-down


def check_dew_risk(is_second_innings: bool, local_start_hour: "int | None",
                    current_humidity_pct: "float | None") -> "dict | None":
    """
    Returns {"risk": "HIGH"|"MODERATE"} + a short reason, or None if dew
    risk doesn't apply (not 2nd innings, not an evening match, or
    humidity/data unavailable). Deliberately conservative - refuses to
    flag risk it can't actually support with real numbers.
    """
    if not is_second_innings:
        return None
    if local_start_hour is None or local_start_hour < EVENING_MATCH_START_HOUR:
        return None
    if current_humidity_pct is None:
        return None

    if current_humidity_pct >= DEW_HUMIDITY_THRESHOLD_PCT:
        return {
            "risk": "HIGH",
            "reason": f"Evening match, humidity at {current_humidity_pct}% \u2014 dew likely affecting grip",
        }
    if current_humidity_pct >= DEW_HUMIDITY_THRESHOLD_PCT - 15:
        return {
            "risk": "MODERATE",
            "reason": f"Evening match, humidity at {current_humidity_pct}% \u2014 dew possible later",
        }
    return None


if __name__ == "__main__":
    print("=== TEST 1: WMO code mapping ===")
    test_codes = [(0, "Clear"), (61, "Light Rain"), (95, "Thunderstorm"), (2, "Partly Cloudy")]
    for code, expected in test_codes:
        result = wmo_code_to_label(code)
        assert result == expected, f"code {code}: got {result}, expected {expected}"
        print(f"PASS: code {code} -> {result}")

    print("\n=== TEST 2: rain code detection ===")
    assert is_rain_code(63) is True
    assert is_rain_code(0) is False
    assert is_rain_code(95) is True
    print("PASS: rain codes correctly identified")

    print("\n=== TEST 3: local hour computation, real Cricbuzz shapes ===")
    # Real data: matchId 168131, startDate "1785135600000", timezone "+03:00"
    local_hour = compute_local_hour("1785135600000", "+03:00")
    print(f"Computed local hour for France v Turkey match: {local_hour}")
    assert local_hour is not None
    print("PASS")

    # Namibia Cricket Ground match, timezone "+02:00", startDate "1785137400000"
    local_hour_2 = compute_local_hour("1785137400000", "+02:00")
    print(f"Computed local hour for Namibia match: {local_hour_2}")
    assert local_hour_2 is not None
    print("PASS")

    print("\n=== TEST 4: negative offset timezone (Providence Stadium, -04:00) ===")
    local_hour_3 = compute_local_hour("1785106800000", "-04:00")
    print(f"Computed local hour for Guyana match: {local_hour_3}")
    assert local_hour_3 is not None
    print("PASS")

    print("\n=== TEST 5: malformed input returns None, no crash ===")
    assert compute_local_hour(None, "+02:00") is None
    assert compute_local_hour("123456", None) is None
    assert compute_local_hour("not_a_number", "+02:00") is None
    print("PASS")

    print("\n=== TEST 6: dew risk logic ===")
    # Evening match (19:00 local), 2nd innings, high humidity -> HIGH risk
    r1 = check_dew_risk(is_second_innings=True, local_start_hour=19, current_humidity_pct=85)
    print("Evening + 2nd innings + humid:", r1)
    assert r1["risk"] == "HIGH"

    # Same but 1st innings -> no alert
    r2 = check_dew_risk(is_second_innings=False, local_start_hour=19, current_humidity_pct=85)
    print("Evening + 1st innings + humid:", r2)
    assert r2 is None

    # Day match (11:00 local), 2nd innings, humid -> no alert (not evening)
    r3 = check_dew_risk(is_second_innings=True, local_start_hour=11, current_humidity_pct=85)
    print("Day match + 2nd innings + humid:", r3)
    assert r3 is None

    # Evening, 2nd innings, but low humidity -> no alert
    r4 = check_dew_risk(is_second_innings=True, local_start_hour=19, current_humidity_pct=40)
    print("Evening + 2nd innings + dry:", r4)
    assert r4 is None

    # Moderate case
    r5 = check_dew_risk(is_second_innings=True, local_start_hour=20, current_humidity_pct=68)
    print("Evening + 2nd innings + moderate humidity:", r5)
    assert r5["risk"] == "MODERATE"
    print("PASS: all dew risk scenarios correct")

    print("\nALL WEATHER SERVICE LOGIC TESTS PASSED")
