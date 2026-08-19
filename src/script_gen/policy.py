"""Instagram-safe content blocklist for scripts and panel prompts."""

from __future__ import annotations

INSTAGRAM_BLOCKLIST = (
    "nudity",
    "nude",
    "naked",
    "lingerie",
    "underwear",
    "porn",
    "sex scene",
    "explicit sex",
    "rape",
    "revenge porn",
    "minor",
    "underage",
    "child porn",
    "suicide method",
    "self-harm",
    "gore",
    "blood splatter",
    "graphic violence",
    "drugged drink",
    "roofie",
    "seduce her",
    "bedroom intimacy",
    "cleavage focus",
)


def policy_violation(text: str) -> str | None:
    lower = (text or "").lower()
    for term in INSTAGRAM_BLOCKLIST:
        if term in lower:
            return f"instagram policy: blocked phrase ({term})"
    return None


def check_script_policy(data: dict) -> str | None:
    blobs = [
        str(data.get("voiceover_script") or ""),
        str(data.get("episode_only_script") or ""),
        str(data.get("caption_hook") or ""),
        str(data.get("caption_teaser") or ""),
    ]
    for panel in data.get("panels") or []:
        if isinstance(panel, dict):
            blobs.append(str(panel.get("dialogue") or ""))
            blobs.append(str(panel.get("scene") or ""))
    for blob in blobs:
        err = policy_violation(blob)
        if err:
            return err
    return None
