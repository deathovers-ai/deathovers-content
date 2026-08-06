"""
F08 — Narration engine with a hard number contract.

Facts come from structured insight objects (Insight Engine). Language may
come from an optional LLM. Every number in the narrated prose MUST appear
in the insight; inventing a figure is a hard fail.

Flow: draft → validate → ≤3 LLM attempts → template fallback.
Never skip the validator. Silence on empty insight; template always validates
against the same allowlist it was built from.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

# Max LLM draft attempts before falling back to the template narrator.
MAX_LLM_ATTEMPTS = 3

# OpenAI-compatible chat completions (Groq / OpenAI / etc.). Offline = template only.
_DEFAULT_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.1-8b-instant"

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def extract_allowed_numbers(insight: dict) -> set[str]:
    """Allowlist of normalized number tokens present in the insight object."""
    allowed: set[str] = set()

    def add(raw: Any) -> None:
        if raw is None or isinstance(raw, bool):
            return
        if isinstance(raw, (int, float)):
            allowed.update(_normalize_token(str(raw)))
            return
        if isinstance(raw, str):
            for match in _NUMBER_RE.findall(raw):
                allowed.update(_normalize_token(match))

    add(insight.get("headline"))
    for key in (
        "diff_pct",
        "projected_low",
        "projected_mid",
        "projected_high",
        "index",
        "percentile",
        "sample_size",
    ):
        if key in insight:
            add(insight.get(key))

    gauge = insight.get("gauge") or {}
    add(gauge.get("batting_pct"))
    add(gauge.get("level"))  # no numbers usually; harmless

    for pointer in insight.get("pointers") or []:
        if not isinstance(pointer, dict):
            continue
        add(pointer.get("value"))
        add(pointer.get("unit"))
        add(pointer.get("pct"))
        add(pointer.get("label"))

    # Nested venue pregame sections
    for section_key in ("toss_record", "score_record", "chase_record", "score_range"):
        section = insight.get(section_key)
        if not isinstance(section, dict):
            continue
        add(section.get("basis"))
        for pointer in section.get("pointers") or []:
            if isinstance(pointer, dict):
                add(pointer.get("value"))
                add(pointer.get("unit"))
                add(pointer.get("pct"))
        for edge in ("low", "high"):
            add(section.get(edge))

    return allowed


def extract_narration_numbers(text: str) -> set[str]:
    """Normalized number tokens found in narrated prose."""
    out: set[str] = set()
    for match in _NUMBER_RE.findall(text or ""):
        out.update(_normalize_token(match))
    return out


def validate_narration(text: str, allowed: set[str]) -> bool:
    """True iff every number in text is in the allowlist (or text has no numbers)."""
    if not text or not str(text).strip():
        return False
    found = extract_narration_numbers(text)
    return found <= allowed


def _normalize_token(token: str) -> set[str]:
    """Accept both '12' and '12.0' forms of the same figure."""
    token = token.strip()
    if not token or token == "-":
        return set()
    forms = {token}
    try:
        num = float(token)
        if num == int(num) and abs(num) < 1e15:
            forms.add(str(int(num)))
            forms.add(f"{int(num)}.0")
        else:
            # Trim trailing zeros: 12.50 → 12.5
            forms.add(("%f" % num).rstrip("0").rstrip("."))
    except ValueError:
        pass
    return forms


def template_narration(insight: dict) -> str:
    """
    Deterministic prose built only from headline + pointers.
    Always validates against extract_allowed_numbers(insight).
    """
    headline = (insight.get("headline") or "").strip().rstrip(".")
    parts = []
    if headline:
        parts.append(headline)
    for pointer in (insight.get("pointers") or [])[:4]:
        if not isinstance(pointer, dict):
            continue
        label = pointer.get("label")
        value = pointer.get("value")
        if label is None or value is None:
            continue
        unit = pointer.get("unit") or ""
        pct = pointer.get("pct")
        bit = f"{label} {value}{unit}"
        if pct is not None:
            sign = "+" if pct > 0 else ""
            bit += f" ({sign}{pct}%)"
        parts.append(bit.strip())
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0] + "."
    return parts[0] + ". " + "; ".join(parts[1:]) + "."


def _llm_enabled() -> bool:
    return bool(os.environ.get("NARRATION_API_KEY") or os.environ.get("GROQ_API_KEY"))


def _default_llm_call(insight: dict) -> str | None:
    """Optional OpenAI-compatible chat call via requests. None on any failure."""
    api_key = os.environ.get("NARRATION_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    url = os.environ.get("NARRATION_API_URL") or _DEFAULT_API_URL
    model = os.environ.get("NARRATION_MODEL") or _DEFAULT_MODEL
    # Payload is the insight only — no external context the model could invent from.
    payload_insight = {
        "type": insight.get("type"),
        "headline": insight.get("headline"),
        "pointers": insight.get("pointers") or [],
        "gauge": insight.get("gauge"),
    }
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write one or two short sentences of cricket match commentary. "
                    "Use ONLY the facts and numbers in the JSON. "
                    "Do not invent, round, or alter any number. "
                    "Do not add stats that are not present. "
                    "Return plain text only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload_insight, ensure_ascii=False),
            },
        ],
    }
    try:
        import requests

        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
        text = (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        ).strip()
        return text or None
    except Exception:
        return None


def narrate_insight(
    insight: dict,
    *,
    llm_call: Callable[[dict], str | None] | None = None,
    max_attempts: int = MAX_LLM_ATTEMPTS,
) -> dict:
    """
    Attach validated `narration` (+ `narration_source`) onto a copy of insight.
    Always runs the validator. Never returns unvalidated LLM prose.
    """
    if not insight:
        return insight
    out = dict(insight)
    allowed = extract_allowed_numbers(out)
    fallback = template_narration(out)
    # Template must itself obey the contract; if somehow empty, leave silent.
    if fallback and not validate_narration(fallback, allowed):
        # Should not happen — refuse rather than emit a bad template.
        out["narration"] = out.get("headline") or ""
        out["narration_source"] = "headline"
        return out

    use_llm = llm_call if llm_call is not None else (
        _default_llm_call if _llm_enabled() else None
    )
    if use_llm:
        for _ in range(max(1, max_attempts)):
            draft = use_llm(out)
            if draft and validate_narration(draft, allowed):
                out["narration"] = draft
                out["narration_source"] = "llm"
                return out

    if fallback:
        out["narration"] = fallback
        out["narration_source"] = "template"
    else:
        out["narration"] = out.get("headline") or ""
        out["narration_source"] = "headline"
    return out


def narrate_insights(
    insights: list,
    *,
    llm_call: Callable[[dict], str | None] | None = None,
    max_attempts: int = MAX_LLM_ATTEMPTS,
) -> list:
    """Narrate a list of insights; non-dicts pass through unchanged."""
    if not insights:
        return insights or []
    return [
        narrate_insight(item, llm_call=llm_call, max_attempts=max_attempts)
        if isinstance(item, dict)
        else item
        for item in insights
    ]


if __name__ == "__main__":
    sample = {
        "type": "venue_score_comparison",
        "headline": "Score is 18% above venue average score",
        "pointers": [
            {"label": "Current Score", "value": "39/3", "unit": " (6.1 ov)"},
            {"label": "Venue Baseline", "value": 33},
            {"label": "Difference", "value": 6.0, "unit": " runs", "pct": 18.2},
            {"label": "Sample Size", "value": 42, "unit": " matches"},
        ],
    }
    allowed = extract_allowed_numbers(sample)
    assert "39" in allowed and "3" in allowed and "18" in allowed
    good = narrate_insight(sample, llm_call=lambda _: "At 39/3 after 6.1 ov, 18% above the venue baseline of 33.")
    assert good["narration_source"] == "llm"
    bad_llm = narrate_insight(
        sample,
        llm_call=lambda _: "They're on 55 for 2, miles ahead.",  # invents 55, 2
        max_attempts=2,
    )
    assert bad_llm["narration_source"] == "template"
    assert validate_narration(bad_llm["narration"], allowed)
    print("narration_engine self-check OK")
