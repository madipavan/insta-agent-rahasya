"""Caption timestamp generation via Whisper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import require_media_duration


@dataclass
class CaptionSegment:
    text: str
    start: float
    end: float
    style: str = "Default"


class CaptionGenerator:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self._model = None

    def generate(self, audio_path: Path) -> list[CaptionSegment]:
        self.logger.start("captions", str(audio_path))
        try:
            from faster_whisper import WhisperModel

            if self._model is None:
                self._model = WhisperModel("small", device="cpu", compute_type="int8")

            lang = "hi" if self.config.voice_language.lower() in ("hindi", "hi") else None
            segments, _ = self._model.transcribe(
                str(audio_path), word_timestamps=True, language=lang
            )
            result: list[CaptionSegment] = []
            for seg in segments:
                if seg.text.strip():
                    result.append(
                        CaptionSegment(
                            text=seg.text.strip(),
                            start=seg.start,
                            end=seg.end,
                        )
                    )
            self.logger.ok("captions", f"{len(result)} segments")
            return result
        except Exception as exc:
            self.logger.warn("captions", f"Whisper failed: {exc}, using fallback")
            return self._fallback_segments(audio_path)

    def _fallback_segments(self, audio_path: Path) -> list[CaptionSegment]:
        duration = require_media_duration(audio_path, label="voiceover")
        self.logger.warn(
            "captions",
            f"using empty caption fallback for full audio ({duration:.1f}s)",
        )
        return [CaptionSegment(text="", start=0.0, end=duration)]
