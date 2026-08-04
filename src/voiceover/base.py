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
        if duration < target_min - 5:
            self.logger.warn(
                "voiceover",
                f"duration {duration:.1f}s below {target_min}s target",
            )
        if duration > target_max + 2:
            raise ValueError(
                f"Voiceover {duration:.1f}s exceeds {target_max}s max "
                f"(Instagram reels must be ≤90s total). Shorten the script."
            )
