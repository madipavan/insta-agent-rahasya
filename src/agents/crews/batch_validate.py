"""Validate batch episode scripts for length, recap, hooks, stock, and hashtags."""

from __future__ import annotations

import re
from typing import Any

from src.script_gen.limits import trim_to_limit

RECAP_PHRASES = (
    "पिछले एपिसोड",
    "पिछली कड़ी",
    "अब तक की कहानी",
    "last episode",
    "previously on",
)

BANNED_OPENING_PREFIXES = (
    "एक दिन",
    "कुछ समय पहले",
    "यह कहानी है",
    "ये कहानी है",
    "एक बार",
    "बहुत साल पहले",
    "once upon a time",
    "this is the story",
    "long ago",
)

MOOD_ONLY_KEYWORDS = frozenset(
    {
        "cinematic",
        "dark",
        "mystery",
        "suspense",
        "thriller",
        "moody",
        "dramatic",
        "atmospheric",
        "noir",
        "tense",
        "ominous",
        "eerie",
        "shadowy",
        "artistic",
    }
)

GENERIC_ON_SCREEN = (
    "एक रहस्यमयी मुलाकात",
    "रहस्यमयी मुलाकात",
    "mysterious meeting",
    "a mysterious meeting",
    "रहस्य",
    "mystery",
    "thriller",
)


def script_body(data: dict[str, Any]) -> str:
    return (data.get("episode_only_script") or data.get("voiceover_script") or "").strip()


def _first_sentence(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[।.!?…])\s+", text, maxsplit=1)
    return (parts[0] if parts else text).strip()


def _coerce_keywords(value: object) -> list[str]:
    from src.book_queue.models import ScriptOutput

    return ScriptOutput._coerce_keywords(value)


def _is_mood_only_keywords(keywords: list[str]) -> bool:
    cleaned = [k.strip().lower() for k in keywords if isinstance(k, str) and k.strip()]
    if not cleaned:
        return True
    # Character-iterated garbage: many 1-char tokens
    if len(cleaned) >= 8 and sum(1 for k in cleaned if len(k) <= 2) >= len(cleaned) * 0.7:
        return True
    non_mood = [k for k in cleaned if k not in MOOD_ONLY_KEYWORDS and len(k) > 2]
    return len(non_mood) == 0


def _on_screen_ok(texts: list[str], hook_body: str) -> str | None:
    if not texts:
        return "missing on_screen_text"
    phrase = (texts[0] or "").strip()
    if not phrase:
        return "empty on_screen_text"
    lower = phrase.lower()
    for generic in GENERIC_ON_SCREEN:
        if phrase == generic or lower == generic.lower():
            return f"generic on_screen_text ({phrase})"
    # Long sentence → not a mute-readable hook phrase
    if len(phrase) > 48 or phrase.count(" ") > 7:
        return "on_screen_text too long (must be short hook phrase)"
    return None


def _has_caption_question(data: dict[str, Any]) -> bool:
    hook = str(data.get("caption_hook") or "")
    teaser = str(data.get("caption_teaser") or "")
    return "?" in hook or "?" in teaser or "？" in hook or "？" in teaser


def _has_bad_brand_hashtag(data: dict[str, Any], brand_hashtag: str) -> bool:
    locked = (brand_hashtag or "#RahasyaExe").strip()
    blobs = [
        str(data.get("static_post_text") or ""),
        str(data.get("caption_hook") or ""),
        str(data.get("caption_teaser") or ""),
        str(data.get("voiceover_script") or ""),
    ]
    joined = " ".join(blobs)
    # Typo / wrong brand forms
    if re.search(r"#\s*rahaysa\s*exe", joined, re.IGNORECASE):
        return True
    for match in re.finditer(r"#\s*rahasya\s*exe", joined, re.IGNORECASE):
        raw = re.sub(r"\s+", "", match.group(0))
        if raw != locked:
            return True
    return False


def validate_script_dict(
    data: dict[str, Any],
    min_chars: int,
    max_chars: int,
    *,
    style_tag: str = "",
    brand_hashtag: str = "#RahasyaExe",
) -> str | None:
    body = script_body(data)
    if not body:
        return "empty voiceover_script"
    length = len(body)
    if length < min_chars:
        return f"too short ({length} < {min_chars})"
    if length > max_chars + 50:
        return f"too long ({length} > {max_chars})"
    lower = body.lower()
    if any(p in body for p in RECAP_PHRASES) or any(p in lower for p in ("last episode", "previously on")):
        return "contains recap phrasing"

    first = _first_sentence(body)
    first_l = first.lower()
    for banned in BANNED_OPENING_PREFIXES:
        if first_l.startswith(banned.lower()) or first.startswith(banned):
            return f"banned opening ({banned})"

    keywords = _coerce_keywords(data.get("stock_keywords"))
    if style_tag:
        style_l = style_tag.lower()
        keywords = [k for k in keywords if k.lower() not in style_l]
    if _is_mood_only_keywords(keywords):
        return "stock_keywords mood-only or invalid (need setting + subject)"

    from src.book_queue.models import ScriptOutput

    on_screen = ScriptOutput._coerce_text_list(data.get("on_screen_text", []))
    on_err = _on_screen_ok(on_screen, first)
    if on_err:
        return on_err

    if not _has_caption_question(data):
        return "caption_hook/teaser missing plot question (?)"

    if _has_bad_brand_hashtag(data, brand_hashtag):
        return f"bad brand hashtag (use {brand_hashtag})"

    return None


def normalize_script_dict(
    data: dict[str, Any],
    max_chars: int,
    *,
    style_tag: str = "",
) -> dict[str, Any]:
    """Trim voiceover fields and mirror episode_only_script."""
    from src.book_queue.models import ScriptOutput

    out = dict(data)
    body = trim_to_limit(script_body(out), max_chars)
    out["voiceover_script"] = body
    out["episode_only_script"] = body
    out["recap_opener"] = ""
    out["hook"] = ScriptOutput._coerce_text(out.get("hook", ""))
    out["cliffhanger"] = ScriptOutput._coerce_text(out.get("cliffhanger", ""))
    out["caption_hook"] = ScriptOutput._coerce_text(out.get("caption_hook", ""))
    out["caption_teaser"] = ScriptOutput._coerce_text(out.get("caption_teaser", ""))
    out["static_post_text"] = ScriptOutput._coerce_text(out.get("static_post_text", ""))
    out["english_voiceover"] = ScriptOutput._coerce_text(out.get("english_voiceover", ""))
    out["on_screen_text"] = ScriptOutput._coerce_text_list(out.get("on_screen_text", []))
    out["english_on_screen"] = ScriptOutput._coerce_text_list(out.get("english_on_screen", []))
    keywords = ScriptOutput._coerce_keywords(out.get("stock_keywords"))
    if style_tag:
        tag = style_tag.strip()
        if tag and not any(tag.lower() in k.lower() or k.lower() in tag.lower() for k in keywords):
            keywords.append(tag)
    out["stock_keywords"] = keywords
    return out


def _token_set(text: str) -> set[str]:
    return {t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split() if len(t) > 3}


def beats_too_similar(a: str, b: str, threshold: float = 0.72) -> bool:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return False
    overlap = len(sa & sb) / max(1, min(len(sa), len(sb)))
    return overlap >= threshold


def find_duplicate_beats(episodes: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Return pairs of episode_num that share near-duplicate plot beats."""
    pairs: list[tuple[int, int]] = []
    for i, ep_a in enumerate(episodes):
        beat_a = ep_a.get("plot_beat_summary") or ep_a.get("hook") or ""
        num_a = int(ep_a.get("episode_num") or i + 1)
        for j in range(i + 1, len(episodes)):
            ep_b = episodes[j]
            beat_b = ep_b.get("plot_beat_summary") or ep_b.get("hook") or ""
            num_b = int(ep_b.get("episode_num") or j + 1)
            if beats_too_similar(beat_a, beat_b):
                pairs.append((num_a, num_b))
    return pairs
