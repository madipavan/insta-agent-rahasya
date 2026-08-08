"""Split long Hindi text into carousel slide chunks."""

from __future__ import annotations

from src.utils.hindi_text import sanitize_hindi_text

__all__ = ["sanitize_hindi_text", "split_into_slides", "cap_slides", "split_into_slides_capped"]


def split_into_slides(text: str, max_chars: int = 110, max_slides: int = 0) -> list[str]:
    """Split voiceover/script into slide-sized Hindi chunks."""
    text = sanitize_hindi_text(text)
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    import re

    sentences = re.split(r"(?<=[।.!?])\s+", text)
    slides: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                slides.append(current.strip())
                current = ""
            for i in range(0, len(sentence), max_chars):
                slides.append(sentence[i : i + max_chars].strip())
            continue

        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                slides.append(current.strip())
            current = sentence

    if current:
        slides.append(current.strip())
    return cap_slides(slides, max_slides)


def cap_slides(slides: list[str], max_slides: int) -> list[str]:
    """Merge slides until count is at most max_slides."""
    if max_slides <= 0 or len(slides) <= max_slides:
        return slides

    merged = slides[:]
    while len(merged) > max_slides:
        # merge the pair with smallest combined length (keeps slides balanced)
        best_idx = 0
        best_len = len(merged[0]) + len(merged[1])
        for i in range(len(merged) - 1):
            pair_len = len(merged[i]) + len(merged[i + 1])
            if pair_len < best_len:
                best_len = pair_len
                best_idx = i
        merged[best_idx] = f"{merged[best_idx]} {merged[best_idx + 1]}".strip()
        del merged[best_idx + 1]
    return merged


def split_into_slides_capped(
    text: str,
    max_chars: int = 100,
    max_slides: int = 10,
) -> list[str]:
    """Split text into at most max_slides carousel chunks."""
    text = sanitize_hindi_text(text)
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    ideal_count = min(max_slides, max(2, -(-len(text) // max_chars)))
    target_chars = max(max_chars, -(-len(text) // ideal_count))
    slides = split_into_slides(text, max_chars=target_chars, max_slides=0)
    if len(slides) <= max_slides:
        return slides

    target_chars = max(max_chars, (len(text) // max_slides) + 1)
    return cap_slides(split_into_slides(text, max_chars=target_chars, max_slides=0), max_slides)
