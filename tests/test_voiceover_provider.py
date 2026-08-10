"""Voiceover provider selection and fallback tests — no paid TTS calls."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.voiceover.edge_tts import EdgeTTSVoiceover
from src.voiceover.provider import FallbackVoiceover, get_voiceover_provider


def _config(tmp_path: Path) -> AppConfig:
    config = AppConfig()
    config.paths.logs_dir = str(tmp_path / "logs")
    config.voice_provider = "elevenlabs"
    config.voice_id = "test-voice-id"
    config.elevenlabs_fallback = True
    config.sarvam_fallback = True
    return config


def test_elevenlabs_missing_key_uses_edge_tts(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.elevenlabs_api_key = ""
    logger = PipelineLogger(tmp_path / "logs")

    provider = get_voiceover_provider(config, logger)

    assert isinstance(provider, EdgeTTSVoiceover)


def test_elevenlabs_missing_key_with_sarvam_prefers_sarvam_chain(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.elevenlabs_api_key = ""
    config.sarvam_api_key = "test-sarvam-key"
    logger = PipelineLogger(tmp_path / "logs")

    provider = get_voiceover_provider(config, logger)

    assert isinstance(provider, FallbackVoiceover)
    assert provider.primary_name == "sarvam"
    assert provider.fallback_name == "edge-tts"


def test_elevenlabs_runtime_missing_key_falls_back(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.elevenlabs_api_key = "present"
    logger = PipelineLogger(tmp_path / "logs")
    edge = EdgeTTSVoiceover(config, logger)
    primary = MagicMock()
    primary.generate.side_effect = ValueError("ELEVENLABS_API_KEY not set in .env")

    with patch.object(edge, "generate", return_value=tmp_path / "out.mp3") as edge_gen:
        fb = FallbackVoiceover(primary, edge, logger, "elevenlabs", "edge-tts")
        out = tmp_path / "voice.mp3"
        result = fb.generate("test", out)

    assert result == tmp_path / "out.mp3"
    edge_gen.assert_called_once()
