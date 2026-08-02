"""Build posting copy — titles, captions, hashtags for reel + carousel."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from src.book_queue.models import EpisodeContext, ScriptOutput
from src.config import AppConfig


@dataclass
class PostDetails:
    novel_title: str
    author: str
    episode_num: int
    total_episodes: int
    reel_title: str
    reel_caption: str
    carousel_title: str
    carousel_caption: str
    hashtags: str
    hook: str
    cliffhanger: str
    static_slide_count: int
    files: dict[str, str]


def _slug_hashtag(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "", text.lower())
    return f"#{slug}" if slug else ""


def build_post_details(
    context: EpisodeContext,
    script: ScriptOutput,
    config: AppConfig,
    caption: str,
    static_slide_count: int = 1,
    hashtags: str | None = None,
) -> PostDetails:
    ep = context.episode.episode_num
    total = context.total_episodes
    novel = context.novel.title
    author = context.novel.author
    quote = script.static_post_text or script.hook

    if hashtags:
        tag_block = hashtags.strip()
    else:
        base_hashtags = config.hashtags.strip()
        extra = " ".join(
            tag
            for tag in (
                f"#ep{ep}",
                _slug_hashtag(novel),
                _slug_hashtag(author),
                "#hindithriller",
                "#suspensestory",
                "#rahaysaexe",
            )
            if tag and tag.lower() not in base_hashtags.lower()
        )
        tag_block = f"{base_hashtags} {extra}".strip()

    reel_title = f'{novel} | Ep {ep}/{total} — {quote}'
    carousel_title = f'{novel} — Part {ep} ({static_slide_count} slides)'

    reel_caption = caption
    if tag_block and tag_block not in caption:
        reel_caption = f"{caption.rstrip()}\n\n{tag_block}"

    carousel_caption = (
        f"{script.caption_hook}\n\n"
        f"{script.caption_teaser}\n\n"
        f"📖 Swipe through {static_slide_count} slides — full story in Hindi.\n\n"
        f'Part {ep}/{total} of "{novel}"\n'
        f"{config.cta}\n\n"
        f"{tag_block}"
    ) if static_slide_count > 1 else reel_caption

    return PostDetails(
        novel_title=novel,
        author=author,
        episode_num=ep,
        total_episodes=total,
        reel_title=reel_title,
        reel_caption=reel_caption,
        carousel_title=carousel_title,
        carousel_caption=carousel_caption,
        hashtags=tag_block,
        hook=script.hook,
        cliffhanger=script.cliffhanger,
        static_slide_count=static_slide_count,
        files={
            "reel": "reel.mp4",
            "reel_cover": "thumbnail.png",
            "voiceover": "voiceover.mp3",
            "transcript": "transcript.txt",
            "carousel_slides": f"static_post_01.png … static_post_{static_slide_count:02d}.png",
        },
    )


def write_post_details_txt(details: PostDetails, output_path: Path) -> Path:
    lines = [
        "=" * 50,
        f"RAHASYA.EXE — POSTING COPY (Episode {details.episode_num})",
        "=" * 50,
        "",
        f"Novel: {details.novel_title}",
        f"Author: {details.author}",
        f"Episode: {details.episode_num} / {details.total_episodes}",
        "",
        "-" * 50,
        "REEL POST",
        "-" * 50,
        "",
        "Title / cover text:",
        details.reel_title,
        "",
        "Caption (copy-paste for Instagram Reel):",
        details.reel_caption,
        "",
        "Upload: reel.mp4",
        "Cover image: thumbnail.png",
        "",
        "-" * 50,
        f"CAROUSEL POST ({details.static_slide_count} slides)",
        "-" * 50,
        "",
        "Title:",
        details.carousel_title,
        "",
        "Caption (copy-paste for Instagram Carousel):",
        details.carousel_caption,
        "",
        f"Upload: static_post_01.png through static_post_{details.static_slide_count:02d}.png",
        "",
        "-" * 50,
        "HASHTAGS (standalone)",
        "-" * 50,
        "",
        details.hashtags,
        "",
        "-" * 50,
        "HOOK & CLIFFHANGER",
        "-" * 50,
        "",
        f"Hook: {details.hook}",
        f"Cliffhanger: {details.cliffhanger}",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_post_details_json(details: PostDetails, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(details), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path
