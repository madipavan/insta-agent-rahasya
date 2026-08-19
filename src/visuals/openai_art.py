"""OpenAI gpt-image panel generation with baked-in speech bubbles."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from src.book_queue.models import StoryPanel
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger


def build_panel_prompt(
    panel: StoryPanel,
    *,
    character_bible: str = "",
    style_tag: str = "",
    series_title: str = "",
) -> str:
    chars = ", ".join(panel.characters) if panel.characters else character_bible
    speaker = (panel.speaker or "the speaking character").strip()
    dialogue = (panel.dialogue or "").strip().replace('"', "'")
    scene = (panel.scene or "Indian domestic scene").strip()
    action = (panel.action or "").strip()
    style = (style_tag or "").strip() or (
        "Indian 2D digital illustration, visual novel webtoon style, clean outlines, "
        "smooth cel shading, warm cinematic lighting, modern Indian characters"
    )
    series = f'Series: "{series_title}". ' if series_title else ""

    bubble_type = "thought bubble" if panel.bubble == "thought" else "speech bubble"
    parts = [
        "Vertical 9:16 2D digital illustration, Indian visual-novel / webtoon style.",
        series + style + ".",
        f"Scene: {scene}.",
    ]
    if action:
        parts.append(f"Action: {action}.")
    if chars:
        parts.append(f"Characters (fully clothed): {chars}.")
    parts.extend([
        "All characters fully clothed. Indian city or village setting. High quality, sharp details.",
        f'Include ONE white oval comic {bubble_type}, thick black outline, small tail pointing to {speaker}.',
        "Place bubble in upper sky area — do not cover faces.",
        f'Inside bubble, bold italic black Roman Hindi/Hinglish text, exactly: "{dialogue}"',
        "Letters must be sharp, centered, fully readable. No misspelling. No extra text anywhere else.",
        "No watermark, no logo, no photorealism, no nudity.",
    ])
    return " ".join(parts)


class OpenAIArtClient:
    def __init__(self, config: AppConfig, logger: PipelineLogger, cache_dir: Path) -> None:
        self.config = config
        self.logger = logger
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        art = getattr(config, "openai_art", None)
        self.enabled = bool(getattr(art, "enabled", True))
        self.model = str(getattr(art, "model", "gpt-image-1") if art else "gpt-image-1")
        self.size = str(getattr(art, "size", "1024x1536") if art else "1024x1536")
        self.quality = str(getattr(art, "quality", "medium") if art else "medium")
        self.style_tag = str(
            getattr(art, "style_tag", "") if art else getattr(config, "stock_style_tag", "")
        )
        self.api_key = (getattr(config, "openai_api_key", "") or "").strip()

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_key)

    def generate_panel(
        self,
        panel: StoryPanel,
        *,
        character_bible: str = "",
        series_title: str = "",
        output_path: Path | None = None,
    ) -> Path | None:
        if not self.available:
            return None

        prompt = build_panel_prompt(
            panel,
            character_bible=character_bible,
            style_tag=self.style_tag,
            series_title=series_title,
        )
        cache_key = hashlib.sha1(f"{self.model}|{self.size}|{prompt}".encode()).hexdigest()[:20]
        out = output_path or (self.cache_dir / f"openai_panel_{cache_key}.png")
        if out.exists() and out.stat().st_size > 0:
            return out

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.images.generate(
                model=self.model,
                prompt=prompt,
                size=self.size,  # type: ignore[arg-type]
                quality=self.quality,  # type: ignore[arg-type]
                n=1,
            )
            item = response.data[0] if response.data else None
            if not item:
                return None
            if getattr(item, "b64_json", None):
                out.write_bytes(base64.b64decode(item.b64_json))
            elif getattr(item, "url", None):
                import requests

                resp = requests.get(str(item.url), timeout=120)
                resp.raise_for_status()
                out.write_bytes(resp.content)
            else:
                return None
            self.logger.info(f"OpenAI panel saved ({self.model}, {self.size})")
            return out
        except Exception as exc:  # noqa: BLE001
            self.logger.warn("openai_art", f"generation failed: {exc}")
            return None
