"""F09 self-check: HIGH dew must raise batting WP; rain must not invent DLS."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from weather_service import DEW_HIGH_WP_DELTA, compute_weather_adjustment
from win_probability import apply_weather_adjustment, load_phase_distributions, simulate_chase

REPORT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "output",
    "context",
    "f09_backtest_report.json",
)


def check(name: str, ok: bool, detail=None) -> None:
    status = "PASS" if ok else "FAIL"
    extra = f" — {detail}" if detail is not None else ""
    print(f"[{status}] {name}{extra}")
    if not ok:
        raise SystemExit(1)


def main() -> int:
    dists = load_phase_distributions()
    check("dists_loaded", bool(dists))

    state = {
        "format": "T20",
        "target": 160,
        "runs": 110,
        "wickets": 4,
        "legal_balls": 84,
        "legal_balls_remaining": 36,
        "runs_required": 50,
        "chase_complete": False,
    }
    import random

    base = simulate_chase(state, dists, n_sims=600, rng=random.Random(9))
    check("base_wp", base is not None)

    high = compute_weather_adjustment({"risk": "HIGH", "reason": "test"}, {"is_rain_code_now": False})
    check("high_dew_adj", high and high["batting_wp_delta"] == DEW_HIGH_WP_DELTA, high)

    adjusted = apply_weather_adjustment(dict(base), high)
    check(
        "dew_raises_wp",
        adjusted["batting_wp"] > base["batting_wp"],
        (base["batting_wp"], adjusted["batting_wp"]),
    )
    check(
        "delta_applied",
        abs(adjusted["batting_wp"] - base["batting_wp"] - DEW_HIGH_WP_DELTA) < 1e-6
        or adjusted["batting_wp"] == 1.0,
    )

    rain = compute_weather_adjustment(None, {"is_rain_code_now": True})
    rain_wp = apply_weather_adjustment(dict(base), rain)
    check("rain_no_wp_delta", rain_wp["batting_wp"] == base["batting_wp"])
    check("rain_uncertain", rain_wp["uncertain"] is True)

    dry = compute_weather_adjustment(None, {"humidity_pct": 40, "is_rain_code_now": False})
    check("dry_silent", dry is None)

    report = {
        "schema": "f09-backtest-v1",
        "base_batting_wp": base["batting_wp"],
        "dew_adjusted_wp": adjusted["batting_wp"],
        "dew_delta": DEW_HIGH_WP_DELTA,
        "rain_preserves_wp": True,
        "notes": "Named-ceiling dew delta + rain uncertainty only; no DLS library in this PR.",
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    print(f"Wrote {REPORT}")
    print(
        f"base={base['batting_wp']:.3f} dew={adjusted['batting_wp']:.3f} "
        f"(+{DEW_HIGH_WP_DELTA})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
