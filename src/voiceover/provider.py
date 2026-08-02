"""Voiceover provider factory."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.voiceover.edge_tts import EdgeTTSVoiceover
from src.voiceover.elevenlabs import ElevenLabsVoiceover


class VoiceoverProvider(Protocol):
    def generate(self, text: str, output_path: Path) -> Path: ...


class FallbackVoiceover:
    def __init__(
        self,
        primary: VoiceoverProvider,
        fallback: VoiceoverProvider,
        logger: PipelineLogger,
        config: AppConfig,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.logger = logger
        self.config = config

    def generate(self, text: str, output_path: Path) -> Path:
        try:
            return self.primary.generate(text, output_path)
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else None
            if code in (401, 402, 429):
                detail = str(exc) if exc.args else f"HTTP {code}"
                self.logger.warn(
                    "voiceover",
                    f"ElevenLabs ({self.config.voice_name}) failed: {detail}",
                )
                if self.config.elevenlabs_fallback:
                    self.logger.warn(
                        "voiceover",
                        "Falling back to edge-tts Hindi. Fix ELEVENLABS_API_KEY for Tarini.",
                    )
                    return self.fallback.generate(text, output_path)
            raise


def get_voiceover_provider(config: AppConfig, logger: PipelineLogger) -> VoiceoverProvider:
    provider = config.voice_provider.lower()
    fallback = EdgeTTSVoiceover(config, logger)

    if provider == "edge-tts":
        return fallback

    elevenlabs = ElevenLabsVoiceover(config, logger)
    if provider in ("elevenlabs", "auto") and config.elevenlabs_api_key and config.voice_id:
        if config.elevenlabs_fallback:
            return FallbackVoiceover(elevenlabs, fallback, logger, config)
        return elevenlabs

    if provider == "elevenlabs":
        return elevenlabs

    return fallback
