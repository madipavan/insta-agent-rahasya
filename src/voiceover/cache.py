"""Voiceover cache — reuse audio to avoid repeat TTS API charges on retries."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger

_META_VERSION = 1


def _stable_hash(parts: list[str]) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def voiceover_fingerprint(text: str, config: AppConfig, provider: str) -> str:
    """Fingerprint a full script + provider settings."""
    parts = [
        provider,
        text.strip(),
        config.voice_id,
        config.voice_name,
        config.voice_language,
        config.elevenlabs_model,
        str(config.elevenlabs_stability),
        str(config.elevenlabs_similarity_boost),
        str(config.elevenlabs_style),
        str(config.elevenlabs_sentence_mode),
        str(config.elevenlabs_cliffhanger_whisper),
        config.sarvam_model,
        config.sarvam_speaker,
        str(config.sarvam_pace),
        str(config.sarvam_temperature),
        config.fish_audio_model,
        config.fish_audio_voice_id,
        str(config.fish_audio_speed),
        str(config.fish_audio_temperature),
        config.edge_tts_voice,
        config.edge_tts_rate,
        config.edge_tts_pitch,
    ]
    return _stable_hash(parts)


def sentence_fingerprint(text: str, config: AppConfig, provider: str) -> str:
    """Fingerprint one spoken sentence/chunk for partial reuse."""
    settings_fp = voiceover_fingerprint("", config, provider)
    return _stable_hash([settings_fp, text.strip()])


def cache_meta_path(audio_path: Path) -> Path:
    return audio_path.with_name(f"{audio_path.name}.cache.json")


def global_cache_meta(config: AppConfig, fingerprint: str) -> Path:
    return config.path("voiceover_cache_dir") / f"{fingerprint}.json"


def global_cache_audio(config: AppConfig, fingerprint: str) -> Path:
    cache_dir = config.path("voiceover_cache_dir")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{fingerprint}.mp3"


def global_sentence_cache_audio(config: AppConfig, fingerprint: str) -> Path:
    cache_dir = config.path("voiceover_cache_dir") / "sentences"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{fingerprint}.mp3"


def read_meta(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_meta(meta_path: Path, payload: dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _audio_usable(path: Path, min_bytes: int = 512) -> bool:
    return path.exists() and path.stat().st_size >= min_bytes


def restore_cached_audio(
    *,
    output_path: Path,
    fingerprint: str,
    config: AppConfig,
    logger: PipelineLogger,
    provider: str,
    char_count: int,
) -> bool:
    """Copy a cached mp3 into output_path when fingerprint matches."""
    sidecar = cache_meta_path(output_path)
    meta = read_meta(sidecar)
    if meta and meta.get("fingerprint") == fingerprint and _audio_usable(output_path):
        logger.info(
            f"voiceover | {provider} cache hit (local) — skipping API "
            f"({char_count} chars saved)"
        )
        return True

    global_audio = global_cache_audio(config, fingerprint)
    global_meta = global_cache_meta(config, fingerprint)
    if not _audio_usable(global_audio):
        return False

    stored = read_meta(global_meta)
    if stored and stored.get("fingerprint") != fingerprint:
        return False

    shutil.copy2(global_audio, output_path)
    if stored:
        write_meta(sidecar, stored)
    else:
        write_meta(
            sidecar,
            {
                "version": _META_VERSION,
                "fingerprint": fingerprint,
                "provider": provider,
                "char_count": char_count,
                "source": "global_cache",
            },
        )
    logger.info(
        f"voiceover | {provider} cache hit (global) — skipping API "
        f"({char_count} chars saved)"
    )
    return True


def persist_cached_audio(
    *,
    output_path: Path,
    fingerprint: str,
    config: AppConfig,
    provider: str,
    char_count: int,
) -> None:
    """Store successful audio locally and in the global cache."""
    if not _audio_usable(output_path):
        return

    payload = {
        "version": _META_VERSION,
        "fingerprint": fingerprint,
        "provider": provider,
        "char_count": char_count,
    }
    write_meta(cache_meta_path(output_path), payload)

    global_audio = global_cache_audio(config, fingerprint)
    if global_audio.resolve() != output_path.resolve():
        shutil.copy2(output_path, global_audio)
        write_meta(global_cache_meta(config, fingerprint), payload)


def restore_sentence_cache(
    *,
    output_path: Path,
    fingerprint: str,
    config: AppConfig,
    logger: PipelineLogger,
    provider: str,
) -> bool:
    cached = global_sentence_cache_audio(config, fingerprint)
    if not _audio_usable(cached):
        return False
    shutil.copy2(cached, output_path)
    logger.info(f"voiceover | {provider} sentence cache hit — skipping API chunk")
    return True


def persist_sentence_cache(*, output_path: Path, fingerprint: str, config: AppConfig) -> None:
    if not _audio_usable(output_path):
        return
    cached = global_sentence_cache_audio(config, fingerprint)
    if cached.resolve() != output_path.resolve():
        shutil.copy2(output_path, cached)
