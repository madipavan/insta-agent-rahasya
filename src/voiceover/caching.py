"""Wrapper that reuses cached voiceover audio before calling paid TTS APIs."""

from __future__ import annotations

from pathlib import Path

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.voiceover.cache import (
    persist_cached_audio,
    restore_cached_audio,
    voiceover_fingerprint,
)


class CachingVoiceover:
    def __init__(
        self,
        inner,
        config: AppConfig,
        logger: PipelineLogger,
        provider_name: str,
    ) -> None:
        self.inner = inner
        self.config = config
        self.logger = logger
        self.provider_name = provider_name

    def generate(self, text: str, output_path: Path) -> Path:
        if not self.config.voiceover_cache:
            return self.inner.generate(text, output_path)

        fingerprint = voiceover_fingerprint(text, self.config, self.provider_name)
        if restore_cached_audio(
            output_path=output_path,
            fingerprint=fingerprint,
            config=self.config,
            logger=self.logger,
            provider=self.provider_name,
            char_count=len(text.strip()),
        ):
            return output_path

        result = self.inner.generate(text, output_path)
        persist_cached_audio(
            output_path=result,
            fingerprint=fingerprint,
            config=self.config,
            provider=self.provider_name,
            char_count=len(text.strip()),
        )
        return result
