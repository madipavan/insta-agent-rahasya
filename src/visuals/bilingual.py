"""Align English parallel text with timed Hindi caption segments / carousel slides."""

from __future__ import annotations

import re

from src.visuals.captions import CaptionSegment


def _split_units(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?…।])\s+", text)
    units = [p.strip() for p in parts if p and p.strip()]
    return units or [text]


def split_parallel(text: str, count: int) -> list[str]:
    """Split text into `count` chunks by sentence units (pad/merge as needed)."""
    if count <= 0:
        return []
    units = _split_units(text)
    if not units:
        return [""] * count
    if len(units) == count:
        return units
    if len(units) < count:
        # Pad by repeating last / empty for extras at end
        out = units[:]
        while len(out) < count:
            out.append(out[-1] if out else "")
        return out[:count]

    # More units than slots — pack by character weight
    total = sum(len(u) for u in units) or 1
    target = total / count
    out: list[str] = []
    bucket: list[str] = []
    bucket_len = 0
    for unit in units:
        if out and len(out) == count - 1:
            bucket.append(unit)
            continue
        if bucket and bucket_len + len(unit) > target * 1.15 and len(out) < count - 1:
            out.append(" ".join(bucket).strip())
            bucket = [unit]
            bucket_len = len(unit)
        else:
            bucket.append(unit)
            bucket_len += len(unit)
    if bucket:
        out.append(" ".join(bucket).strip())
    while len(out) < count:
        out.append("")
    return out[:count]


def make_bilingual_segments(
    hindi_segments: list[CaptionSegment],
    english_voiceover: str,
    *,
    english_on_screen: list[str] | None = None,
) -> list[CaptionSegment]:
    """Attach English lines under Hindi (newline-separated) using Whisper timings."""
    if not hindi_segments:
        return hindi_segments

    en = (english_voiceover or "").strip()
    hook_en = ""
    if english_on_screen:
        hook_en = (english_on_screen[0] or "").strip()

    has_hook = bool(hindi_segments and hindi_segments[0].style == "Hook")
    if has_hook and len(hindi_segments) > 1:
        body_parts = (
            split_parallel(en, len(hindi_segments) - 1)
            if en
            else [""] * (len(hindi_segments) - 1)
        )
        if hook_en:
            en_parts = [hook_en] + body_parts
        elif en:
            en_parts = split_parallel(en, len(hindi_segments))
        else:
            en_parts = [""] * len(hindi_segments)
    else:
        en_parts = split_parallel(en, len(hindi_segments)) if en else [""] * len(hindi_segments)
        if has_hook and hook_en:
            en_parts[0] = hook_en

    out: list[CaptionSegment] = []
    for seg, en_line in zip(hindi_segments, en_parts):
        hi = (seg.text or "").strip()
        # Avoid duplicating English if Hindi already carries a second line
        if "\n" in hi:
            text = hi
        else:
            en_line = (en_line or "").strip()
            text = f"{hi}\n{en_line}" if hi and en_line else (hi or en_line)
        out.append(CaptionSegment(text=text, start=seg.start, end=seg.end, style=seg.style))
    return out


def bilingual_slide_texts(hindi_slides: list[str], english_slides: list[str]) -> list[str]:
    """Pair Hindi + English carousel chunks (compact dual-language slide text)."""
    if not english_slides:
        return hindi_slides
    n = len(hindi_slides)
    en = english_slides[:n]
    while len(en) < n:
        en.append("")
    paired: list[str] = []
    for hi, eng in zip(hindi_slides, en):
        hi = (hi or "").strip()
        eng = (eng or "").strip()
        if hi and eng:
            paired.append(f"{hi}\n\n{eng}")
        else:
            paired.append(hi or eng)
    return paired
