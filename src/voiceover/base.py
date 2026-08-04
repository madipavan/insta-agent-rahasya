"""Shared voiceover helpers."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.limits import INSTAGRAM_MAX_REEL_SEC
from src.utils.ffmpeg_path import get_ffmpeg_exe, require_media_duration


class VoiceoverBase:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger

    def _get_duration(self, audio_path: Path) -> float:
        return require_media_duration(audio_path, label="voiceover")

    def _enforce_max_duration(self, audio_path: Path, duration: float) -> float:
        """Trim voiceover to script_max_seconds when TTS runs long (dramatic pauses, etc.)."""
        target_max = float(self.config.script_max_seconds)
        ig_cap = float(getattr(self.config.video, "instagram_max_sec", INSTAGRAM_MAX_REEL_SEC))
        hard_cap = min(target_max, ig_cap - 2.0)

        if duration <= hard_cap + 1.0:
            return duration

        self.logger.warn(
            "voiceover",
            f"duration {duration:.1f}s exceeds {hard_cap:.0f}s — trimming audio",
        )
        trimmed = audio_path.with_name(f"{audio_path.stem}_trimmed{audio_path.suffix}")
        result = subprocess.run(
            [
                get_ffmpeg_exe(),
                "-y",
                "-i",
                str(audio_path),
                "-t",
                str(hard_cap),
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(trimmed),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"voiceover trim failed: {result.stderr[-500:]}")
        shutil.move(str(trimmed), str(audio_path))
        return self._get_duration(audio_path)

    def _check_duration(self, duration: float) -> None:
        target_min = self.config.script_min_seconds
        if duration < target_min - 8:
            self.logger.warn(
                "voiceover",
                f"duration {duration:.1f}s below {target_min}s target",
            )
