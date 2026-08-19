"""Data models for novels and episodes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StoryPanel:
    dialogue: str
    scene: str
    speaker: str = ""
    characters: list[str] = field(default_factory=list)
    bubble: str = "speech"
    action: str = ""


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
    pdf_path: str = ""


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
    script_json: str = ""


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
    english_voiceover: str = ""
    english_on_screen: list[str] = field(default_factory=list)
    panels: list[StoryPanel] = field(default_factory=list)

    @staticmethod
    def _coerce_panels(value: object) -> list[StoryPanel]:
        if not value:
            return []
        if not isinstance(value, (list, tuple)):
            return []
        out: list[StoryPanel] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            dialogue = ScriptOutput._coerce_text(item.get("dialogue", ""))
            scene = ScriptOutput._coerce_text(item.get("scene", ""))
            if not dialogue or not scene:
                continue
            chars_raw = item.get("characters", [])
            characters: list[str] = []
            if isinstance(chars_raw, str) and chars_raw.strip():
                characters = [chars_raw.strip()]
            elif isinstance(chars_raw, (list, tuple)):
                characters = [
                    ScriptOutput._coerce_text(c) for c in chars_raw if ScriptOutput._coerce_text(c)
                ]
            out.append(
                StoryPanel(
                    dialogue=dialogue,
                    scene=scene,
                    speaker=ScriptOutput._coerce_text(item.get("speaker", "")),
                    characters=characters,
                    bubble=ScriptOutput._coerce_text(item.get("bubble", "speech")) or "speech",
                    action=ScriptOutput._coerce_text(item.get("action", "")),
                )
            )
        return out

    @staticmethod
    def _coerce_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("text", "hook", "line", "caption", "value"):
                if key in value and isinstance(value[key], str):
                    return value[key].strip()
            return ""
        if isinstance(value, (list, tuple)):
            for item in value:
                text = ScriptOutput._coerce_text(item)
                if text:
                    return text
            return ""
        return str(value).strip()

    @staticmethod
    def _coerce_text_list(value: object) -> list[str]:
        if not value:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, dict):
            text = ScriptOutput._coerce_text(value)
            return [text] if text else []
        if isinstance(value, (list, tuple)):
            out: list[str] = []
            for item in value:
                text = ScriptOutput._coerce_text(item)
                if text:
                    out.append(text)
            return out
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _coerce_keywords(value: object) -> list[str]:
        """Parse stock keywords; split comma-separated strings (never char-iterate)."""
        if value is None:
            return []
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",")]
            return [p for p in parts if p]
        if isinstance(value, (list, tuple)):
            out: list[str] = []
            for item in value:
                if isinstance(item, str):
                    # LLM sometimes returns one comma-joined element
                    if "," in item and len(item) > 24:
                        out.extend(p.strip() for p in item.split(",") if p.strip())
                    elif item.strip():
                        out.append(item.strip())
                else:
                    text = ScriptOutput._coerce_text(item)
                    if text:
                        out.append(text)
            return out
        text = str(value).strip()
        return [text] if text else []

    @classmethod
    def from_dict(cls, data: dict) -> "ScriptOutput":
        keywords = [
            k
            for k in cls._coerce_keywords(data.get("stock_keywords"))
            if k.lower() not in ("esmodule", "module", "default")
        ]
        episode_only = cls._coerce_text(data.get("episode_only_script", ""))
        voiceover = cls._coerce_text(data.get("voiceover_script", ""))
        recap = cls._coerce_text(data.get("recap_opener", ""))

        body = episode_only or voiceover
        if recap and body.startswith(recap):
            body = body[len(recap) :].strip()
        elif recap:
            body = body.replace(recap, "", 1).strip()

        if not body:
            body = voiceover

        return cls(
            hook=cls._coerce_text(data.get("hook", "")),
            voiceover_script=body,
            cliffhanger=cls._coerce_text(data.get("cliffhanger", "")),
            caption_hook=cls._coerce_text(data.get("caption_hook", "")),
            caption_teaser=cls._coerce_text(data.get("caption_teaser", "")),
            static_post_text=cls._coerce_text(data.get("static_post_text", "")),
            stock_keywords=keywords,
            on_screen_text=cls._coerce_text_list(data.get("on_screen_text", [])),
            recap_opener="",
            episode_only_script=body,
            english_voiceover=cls._coerce_text(data.get("english_voiceover", "")),
            english_on_screen=cls._coerce_text_list(data.get("english_on_screen", [])),
            panels=cls._coerce_panels(data.get("panels", [])),
        )

    def episode_script(self) -> str:
        """Today's episode Hindi script — reel audio + carousel. No recap."""
        return (self.episode_only_script or self.voiceover_script).strip()

    def carousel_source(self) -> str:
        """Alias for episode_script — static carousel slides."""
        return self.episode_script()
