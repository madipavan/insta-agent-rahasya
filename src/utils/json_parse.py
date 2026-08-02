"""Parse JSON from LLM responses — handles fences, extraction, control chars."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse JSON from LLM output, tolerating markdown fences and raw newlines in strings."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    for candidate in (text, _extract_json_object(text)):
        if not candidate:
            continue
        for attempt in (candidate, _sanitize_control_chars(candidate)):
            try:
                result = json.loads(attempt)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("Could not parse LLM JSON", text, 0)


def _extract_json_object(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group() if match else None


def _sanitize_control_chars(text: str) -> str:
    """Escape unescaped control characters inside JSON string literals."""
    result: list[str] = []
    in_string = False
    escape = False

    for ch in text:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == "\\":
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            if ord(ch) < 32:
                result.append(f"\\u{ord(ch):04x}")
                continue
        result.append(ch)

    return "".join(result)
