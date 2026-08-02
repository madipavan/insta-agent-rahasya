"""Export script bundle as human-readable script.txt."""

from __future__ import annotations

from pathlib import Path

from src.book_queue.models import EpisodeContext, ScriptOutput


def write_script_txt(
    context: EpisodeContext,
    script: ScriptOutput,
    output_path: Path,
    caption: str = "",
) -> Path:
    episode_body = script.episode_script()
    lines = [
        "=== Rahasya.exe — Episode Script ===",
        f"Novel: {context.novel.title}",
        f"Author: {context.novel.author}",
        f"Episode: {context.episode.episode_num} / {context.total_episodes}",
        "",
        "--- TODAY'S EPISODE (reel voiceover + carousel static posts) ---",
        episode_body,
        "",
        "--- HOOK ---",
        script.hook,
        "",
        "--- CLIFFHANGER ---",
        script.cliffhanger,
        "",
        "--- CAPTION HOOK ---",
        script.caption_hook,
        "",
        "--- CAPTION TEASER ---",
        script.caption_teaser,
        "",
        "--- STATIC QUOTE ---",
        script.static_post_text,
        "",
        "--- ON-SCREEN TEXT ---",
        *script.on_screen_text,
        "",
        "--- STOCK KEYWORDS ---",
        ", ".join(script.stock_keywords),
        "",
    ]

    if caption:
        lines += ["--- FULL CAPTION (Instagram) ---", caption, ""]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_transcript_txt(spoken_text: str, output_path: Path) -> Path:
    """Exact words spoken in voiceover.mp3 / reel audio."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(spoken_text.strip(), encoding="utf-8")
    return output_path
