"""Data models for novels and episodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Novel:
    id: int
    title: str
    author: str
    country: str
    chapter_count: int
    public_domain: bool
    source_link: str
    adaptation_checked: bool
    estimated_episodes: int
    status: str
    current_episode: int = 0
    novel_logline: str = ""
    story_summary: str = ""
    retention_strategy: str = ""


@dataclass
class Episode:
    id: int
    novel_id: int
    episode_num: int
    chapter_start: int
    chapter_end: int
    plot_beat_summary: str
    cumulative_synopsis: str
    status: str
    planned_hook: str = ""
    planned_cliffhanger: str = ""
    retention_angle: str = ""


@dataclass
class EpisodeContext:
    novel: Novel
    episode: Episode
    total_episodes: int


@dataclass
class ScriptOutput:
    hook: str
    voiceover_script: str
    cliffhanger: str
    caption_hook: str
    caption_teaser: str
    static_post_text: str
    stock_keywords: list[str]
    on_screen_text: list[str]
    recap_opener: str = ""
    episode_only_script: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptOutput":
        keywords = [k for k in data.get("stock_keywords", ["night", "shadow"]) if isinstance(k, str)]
        keywords = [k for k in keywords if k.lower() not in ("esmodule", "module", "default")]
        if not keywords:
            keywords = ["cinematic", "dark", "mystery"]
        episode_only = data.get("episode_only_script", "")
        voiceover = data.get("voiceover_script", "")
        recap = data.get("recap_opener", "")

        body = episode_only.strip() or voiceover.strip()
        if recap and body.startswith(recap.strip()):
            body = body[len(recap.strip()) :].strip()
        elif recap:
            body = body.replace(recap, "", 1).strip()

        if not body:
            body = voiceover.strip()

        return cls(
            hook=data.get("hook", ""),
            voiceover_script=body,
            cliffhanger=data.get("cliffhanger", ""),
            caption_hook=data.get("caption_hook", ""),
            caption_teaser=data.get("caption_teaser", ""),
            static_post_text=data.get("static_post_text", ""),
            stock_keywords=keywords,
            on_screen_text=data.get("on_screen_text", []),
            recap_opener="",
            episode_only_script=body,
        )

    def episode_script(self) -> str:
        """Today's episode Hindi script — reel audio + carousel. No recap."""
        return (self.episode_only_script or self.voiceover_script).strip()

    def carousel_source(self) -> str:
        """Alias for episode_script — static carousel slides."""
        return self.episode_script()
