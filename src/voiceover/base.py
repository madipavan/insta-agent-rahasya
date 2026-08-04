"""Shared voiceover helpers."""

from __future__ import annotations

from pathlib import Path

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import require_media_duration


class VoiceoverBase:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger

    def _get_duration(self, audio_path: Path) -> float:
        return require_media_duration(audio_path, label="voiceover")

    def _check_duration(self, duration: float) -> None:
        target_min = self.config.script_min_seconds
        target_max = self.config.script_max_seconds
        if duration < target_min or duration > target_max + 15:
            self.logger.warn(
                "voiceover",
                f"duration {duration:.1f}s outside {target_min}-{target_max}s target",
            )
