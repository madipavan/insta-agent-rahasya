"""Shared voiceover helpers."""

from __future__ import annotations

from pathlib import Path

from src.utils.ffmpeg_path import get_media_duration
from src.pipeline.logger import PipelineLogger


class VoiceoverBase:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger

    def _get_duration(self, audio_path: Path) -> float:
        duration = get_media_duration(audio_path)
        return duration if duration is not None else 25.0

    def _check_duration(self, duration: float) -> None:
        target_min = self.config.script_min_seconds
        target_max = self.config.script_max_seconds
        if duration < target_min or duration > target_max + 15:
            self.logger.warn(
                "voiceover",
                f"duration {duration:.1f}s outside {target_min}-{target_max}s target",
            )
