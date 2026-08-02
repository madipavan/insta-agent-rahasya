"""Script length limits for reel + carousel constraints."""

from __future__ import annotations

import re

from src.config import AppConfig

# Hindi edge-tts ~11 chars/second average
CHARS_PER_SECOND = 11


def script_char_limits(config: AppConfig) -> tuple[int, int]:
    """Return (min_chars, max_chars) for voiceover/carousel text."""
    min_chars = config.script_min_seconds * CHARS_PER_SECOND
    max_chars = config.script_max_seconds * CHARS_PER_SECOND
    carousel_cap = config.static_post.max_slides * config.static_post.chars_per_slide
    return min_chars, min(max_chars, carousel_cap)


def max_reel_duration_sec(config: AppConfig) -> float:
    """Total reel length including intro/outro cards."""
    return (
        config.script_max_seconds
        + config.brand.intro_duration_sec
        + config.brand.outro_duration_sec
    )


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
