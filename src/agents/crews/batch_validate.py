"""Validate batch episode scripts for length, recap, and uniqueness."""

from __future__ import annotations

from typing import Any

from src.script_gen.limits import trim_to_limit

RECAP_PHRASES = (
    "पिछले एपिसोड",
    "पिछली कड़ी",
    "अब तक की कहानी",
    "last episode",
    "previously on",
)


def script_body(data: dict[str, Any]) -> str:
    return (data.get("episode_only_script") or data.get("voiceover_script") or "").strip()


def validate_script_dict(data: dict[str, Any], min_chars: int, max_chars: int) -> str | None:
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
    return None


def normalize_script_dict(data: dict[str, Any], max_chars: int) -> dict[str, Any]:
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
    out["on_screen_text"] = ScriptOutput._coerce_text_list(out.get("on_screen_text", []))
    if not isinstance(out.get("stock_keywords"), list):
        out["stock_keywords"] = ["cinematic", "dark", "mystery"]
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
