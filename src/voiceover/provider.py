"""Voiceover provider factory."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.voiceover.edge_tts import EdgeTTSVoiceover
from src.voiceover.elevenlabs import ElevenLabsVoiceover
from src.voiceover.fish_audio import FishAudioVoiceover
from src.voiceover.sarvam import SarvamVoiceover


class VoiceoverProvider(Protocol):
    def generate(self, text: str, output_path: Path) -> Path: ...


class FallbackVoiceover:
    def __init__(
        self,
        primary: VoiceoverProvider,
        fallback: VoiceoverProvider,
        logger: PipelineLogger,
        primary_name: str,
        fallback_name: str = "edge-tts",
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.logger = logger
        self.primary_name = primary_name
        self.fallback_name = fallback_name

    def generate(self, text: str, output_path: Path) -> Path:
        try:
            return self.primary.generate(text, output_path)
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else None
            if code in (401, 402, 403, 429):
                detail = str(exc) if exc.args else f"HTTP {code}"
                self.logger.warn(
                    "voiceover",
                    f"{self.primary_name} failed: {detail}",
                )
                self.logger.warn(
                    "voiceover",
                    f"Falling back to {self.fallback_name}.",
                )
                return self.fallback.generate(text, output_path)
            raise


def get_voiceover_provider(config: AppConfig, logger: PipelineLogger) -> VoiceoverProvider:
    provider = config.voice_provider.lower()
    fallback = EdgeTTSVoiceover(config, logger)

    if provider == "edge-tts":
        return fallback

    if provider == "fish-audio":
        fish = FishAudioVoiceover(config, logger)
        if config.fish_audio_fallback:
            return FallbackVoiceover(fish, fallback, logger, "fish-audio")
        return fish

    if provider == "sarvam":
        sarvam = SarvamVoiceover(config, logger)
        if config.sarvam_fallback:
            return FallbackVoiceover(sarvam, fallback, logger, "sarvam")
        return sarvam

    elevenlabs = ElevenLabsVoiceover(config, logger)
    if provider in ("elevenlabs", "auto") and config.elevenlabs_api_key and config.voice_id:
        if config.elevenlabs_fallback:
            return FallbackVoiceover(elevenlabs, fallback, logger, "elevenlabs")
        return elevenlabs

    if provider == "elevenlabs":
        return elevenlabs

    return fallback
