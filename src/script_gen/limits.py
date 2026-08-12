"""Script length limits for reel + carousel constraints."""

from __future__ import annotations

import re

from src.config import AppConfig

# Hindi/Hinglish TTS: ~10–11 chars/s for natural spoken density at 75–80s
CHARS_PER_SECOND_MIN = 10
CHARS_PER_SECOND_MAX = 11
INSTAGRAM_MAX_REEL_SEC = 90


def script_char_limits(config: AppConfig) -> tuple[int, int]:
    """Return (min_chars, max_chars) for voiceover length."""
    min_chars = config.script_min_seconds * CHARS_PER_SECOND_MIN
    max_chars = config.script_max_seconds * CHARS_PER_SECOND_MAX
    return min_chars, max_chars


def max_reel_duration_sec(config: AppConfig) -> float:
    """Total reel length including intro/outro cards (capped for Instagram API)."""
    target = (
        config.script_max_seconds
        + config.brand.intro_duration_sec
        + config.brand.outro_duration_sec
    )
    ig_cap = getattr(config.video, "instagram_max_sec", INSTAGRAM_MAX_REEL_SEC)
    return min(target, float(ig_cap))


def trim_to_limit(text: str, max_chars: int) -> str:
    """Trim Hindi script at sentence boundary without mid-word cuts."""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    sentences = re.split(r"(?<=[।.!?])\s+", text)
    result = ""
    for sentence in sentences:
        candidate = f"{result} {sentence}".strip() if result else sentence
        if len(candidate) <= max_chars:
            result = candidate
        else:
            break

    if result:
        return result

    return text[:max_chars].rsplit(" ", 1)[0].strip() or text[:max_chars]
