"""BGM pipeline tests — no ElevenLabs credits required."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.book_queue.models import Novel
from src.book_queue.store import Database
from src.config import AppConfig
from src.novel_assets.bgm import _generate_novel_pad
from src.novel_assets.manager import NovelAssetManager
from src.pipeline.logger import PipelineLogger
from src.scheduler.meta import MetaScheduler
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.visuals.assembler import ReelAssembler
from src.visuals.bgm_audio import (
    bgm_band_delta_db,
    has_audible_bgm_bed,
    probe_audio_codec,
)


def _ffmpeg(args: list[str]) -> None:
    subprocess.run([get_ffmpeg_exe(), *args], check=True, capture_output=True, text=True)


def _make_tone_mp3(path: Path, freq: int, duration: float = 12.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([
        "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
        "-q:a", "4", str(path),
    ])


def _make_voice_mp3(path: Path, duration: float = 8.0) -> None:
    """Speech-like low-mid energy without calling any TTS API."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg([
        "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=180:duration={duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency=360:duration={duration}",
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first",
        "-q:a", "4",
        str(path),
    ])


@pytest.fixture
def asm(tmp_path: Path) -> ReelAssembler:
    config = AppConfig()
    config.paths.logs_dir = str(tmp_path / "logs")
    logger = PipelineLogger(tmp_path / "logs")
    return ReelAssembler(config, logger)


def test_mix_adds_detectable_bgm_band(asm: ReelAssembler, tmp_path: Path) -> None:
    voice = tmp_path / "voice.mp3"
    bgm = tmp_path / "bgm.mp3"
    padded = tmp_path / "padded.aac"
    mixed = tmp_path / "mixed.aac"

    _make_voice_mp3(voice)
    _make_tone_mp3(bgm, freq=3200)

    asm._pad_audio(voice, padded, delay_sec=1.0, pad_end_sec=1.0)
    asm._mix_bgm(padded, bgm, mixed)

    delta = bgm_band_delta_db(mixed, padded, highpass_hz=2500, start_sec=2.0, duration_sec=2.0)
    assert delta is not None
    assert delta >= 3.0, f"BGM bed not detectable in mix (delta={delta:.1f}dB)"
    assert has_audible_bgm_bed(mixed, padded, start_sec=2.0, duration_sec=2.0)


def test_missing_bgm_file_skips_mix(asm: ReelAssembler, tmp_path: Path) -> None:
    voice = tmp_path / "voice.mp3"
    padded = tmp_path / "padded.aac"
    _make_voice_mp3(voice, duration=4.0)
    asm._pad_audio(voice, padded, delay_sec=1.0, pad_end_sec=1.0)

    missing = tmp_path / "nope.mp3"
    assert not missing.exists()

    # Assembler branch: bgm_path set but missing → voice-only path (no exception).
    boosted = tmp_path / "boosted.aac"
    asm._boost_voice(padded, boosted, gain=1.1)
    assert boosted.exists()
    delta = bgm_band_delta_db(boosted, padded, highpass_hz=2500, start_sec=1.5, duration_sec=1.0)
    assert delta is not None
    assert abs(delta) < 2.0


def test_synthetic_pad_audible_in_mid_band(asm: ReelAssembler, tmp_path: Path) -> None:
    """Synthetic CI fallback must be audible after mix (not sub-bass only)."""
    novel = Novel(
        id=1,
        title="Audibility Test",
        author="Tester",
        country="IN",
        chapter_count=8,
        public_domain=True,
        source_link="",
        adaptation_checked=True,
        estimated_episodes=4,
        status="active",
    )
    voice = tmp_path / "voice.mp3"
    bgm = tmp_path / "bgm.mp3"
    padded = tmp_path / "padded.aac"
    mixed = tmp_path / "mixed.aac"

    _make_voice_mp3(voice, duration=8.0)
    _generate_novel_pad(bgm, novel)
    asm._pad_audio(voice, padded, delay_sec=1.0, pad_end_sec=1.0)
    asm._mix_bgm(padded, bgm, mixed)

    delta = bgm_band_delta_db(mixed, padded, highpass_hz=1000, start_sec=2.0, duration_sec=2.0)
    assert delta is not None
    assert delta >= 3.0, f"synthetic pad inaudible in mid band (delta={delta:.1f}dB)"


def test_ensure_bgm_creates_file_when_fetch_fails(tmp_path: Path) -> None:
    config = AppConfig()
    data = tmp_path / "data"
    config.paths.data_dir = str(data)
    config.paths.db_path = str(data / "test.db")
    config.paths.stock_library = str(tmp_path / "assets" / "stock_library")
    logger = PipelineLogger(tmp_path / "logs")
    db = Database(config.path("db_path"))
    mgr = NovelAssetManager(config, logger, db)

    novel = Novel(
        id=99,
        title="Pipeline Test",
        author="Tester",
        country="IN",
        chapter_count=8,
        public_domain=True,
        source_link="",
        adaptation_checked=True,
        estimated_episodes=4,
        status="active",
    )

    with patch("src.novel_assets.manager.fetch_novel_bgm", return_value=None):
        assets = mgr.ensure(novel, ["mystery", "thriller"])

    assert assets.bgm_path is not None
    assert assets.bgm_path.exists()
    assert assets.bgm_path.stat().st_size > 1000


def test_meta_prepare_preserves_bgm_bed(asm: ReelAssembler, tmp_path: Path) -> None:
    voice = tmp_path / "voice.mp3"
    bgm = tmp_path / "bgm.mp3"
    padded = tmp_path / "padded.aac"
    mixed = tmp_path / "mixed.aac"
    reel = tmp_path / "reel.mp4"

    _make_voice_mp3(voice, duration=6.0)
    _make_tone_mp3(bgm, freq=3500, duration=20.0)
    asm._pad_audio(voice, padded, delay_sec=0.5, pad_end_sec=0.5)
    asm._mix_bgm(padded, bgm, mixed)

    _ffmpeg([
        "-y",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=6",
        "-i", str(mixed),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(reel),
    ])

    config = AppConfig()
    config.paths.logs_dir = str(tmp_path / "logs")
    meta = MetaScheduler(config, PipelineLogger(tmp_path / "logs"))

    before = bgm_band_delta_db(mixed, padded, highpass_hz=2500, start_sec=1.0, duration_sec=2.0)
    prepared = meta._prepare_reel_for_instagram(reel)
    codec = probe_audio_codec(prepared)
    assert codec == "aac", f"expected aac audio stream, got {codec!r}"

    extracted = tmp_path / "prepared.aac"
    _ffmpeg(["-y", "-i", str(prepared), "-vn", "-c:a", "copy", str(extracted)])

    after = bgm_band_delta_db(extracted, padded, highpass_hz=2500, start_sec=1.0, duration_sec=2.0)
    assert before is not None and after is not None
    assert after >= before - 2.0, (
        f"Instagram prep removed BGM bed (before={before:.1f}dB delta, after={after:.1f}dB)"
    )


def test_stream_loop_mix_not_silent_vs_aloop(asm: ReelAssembler, tmp_path: Path) -> None:
    """Regression: BGM input must loop; stream_loop path must not output silence."""
    voice = tmp_path / "voice.mp3"
    bgm = tmp_path / "bgm.mp3"
    padded = tmp_path / "padded.aac"
    mixed = tmp_path / "mixed.aac"

    _make_voice_mp3(voice, duration=5.0)
    _make_tone_mp3(bgm, freq=4000, duration=3.0)

    asm._pad_audio(voice, padded, delay_sec=1.0, pad_end_sec=1.0)
    asm._mix_bgm(padded, bgm, mixed)

    intro_bed = asm._measure_mean_volume(mixed, start_sec=0.2, duration_sec=0.5)
    assert intro_bed is not None
    assert intro_bed > -45.0, f"intro bed silent ({intro_bed:.1f}dB)"
