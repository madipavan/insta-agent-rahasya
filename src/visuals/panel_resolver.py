"""Generate comic panels for Indian dark-serial reels via OpenAI."""

from __future__ import annotations

from pathlib import Path

from src.book_queue.models import EpisodeContext, ScriptOutput
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.visuals.openai_art import OpenAIArtClient


def is_panel_mode(config: AppConfig) -> bool:
    return getattr(config, "content_mode", "") == "indian_dark_serial"


class PanelResolver:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        cache = config.path("output_dir") / "panel_cache"
        self.openai = OpenAIArtClient(config, logger, cache)

    def resolve_panels(
        self,
        script: ScriptOutput,
        context: EpisodeContext,
        output_dir: Path,
    ) -> list[Path]:
        panels = script.panels
        if not panels:
            raise RuntimeError("panel mode requires script.panels")

        output_dir.mkdir(parents=True, exist_ok=True)
        bible = _character_bible(context)
        series = context.novel.title
        max_retries = int(getattr(getattr(self.config, "openai_art", None), "max_retries", 2) or 2)

        self.logger.start("panels", f"{len(panels)} OpenAI panels for {series}")
        paths: list[Path] = []
        for i, panel in enumerate(panels):
            out = output_dir / f"panel_{i + 1:02d}.png"
            saved: Path | None = None
            for attempt in range(max_retries + 1):
                saved = self.openai.generate_panel(
                    panel,
                    character_bible=bible,
                    series_title=series,
                    output_path=out,
                )
                if saved:
                    break
                self.logger.warn("panels", f"panel {i + 1} attempt {attempt + 1} failed — retrying")
            if not saved:
                raise RuntimeError(f"Failed to generate panel {i + 1}/{len(panels)}")
            paths.append(saved)

        self.logger.ok("panels", f"{len(paths)} panels")
        return paths


def _character_bible(context: EpisodeContext) -> str:
    parts = [
        context.novel.story_summary,
        context.novel.novel_logline,
        context.novel.retention_strategy,
    ]
    bible = " ".join(p.strip() for p in parts if p and p.strip())
    return bible[:800]
