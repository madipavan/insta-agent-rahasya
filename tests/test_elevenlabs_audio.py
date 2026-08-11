"""Tests for per-novel ElevenLabs music + SFX generation (mocked — no credits)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.book_queue.models import Novel
from src.book_queue.store import Database
from src.config import AppConfig
from src.novel_assets.elevenlabs_audio import (
    generate_novel_music,
    generate_novel_sfx,
    music_prompt,
    novel_sfx_complete,
)
from src.novel_assets.manager import NovelAssetManager
from src.pipeline.logger import PipelineLogger
from src.visuals.sfx import SFX_FILES


def _novel(nid: int = 42) -> Novel:
    return Novel(
        id=nid,
        title="The Riddle of the Sands",
        author="Erskine Childers",
        country="UK",
        chapter_count=12,
        public_domain=True,
        source_link="",
        adaptation_checked=True,
        estimated_episodes=12,
        status="active",
    )


def test_music_prompt_is_instrumental():
    prompt = music_prompt(_novel(), ["boat chase", "storm"])
    assert "instrumental" in prompt.lower() or "Instrumental" in prompt
    assert "no vocals" in prompt.lower()
    assert "Riddle" in prompt


def test_generate_novel_music_writes_cache(tmp_path: Path):
    config = AppConfig()
    config.elevenlabs_api_key = "test-key"
    config.elevenlabs_music_length_ms = 15000
    logger = PipelineLogger(tmp_path / "logs")
    out = tmp_path / "bgm.mp3"
    fake_audio = b"ID3" + b"\x00" * 2000

    with patch("src.novel_assets.elevenlabs_audio.requests.post") as post:
        resp = MagicMock()
        resp.status_code = 200
        resp.content = fake_audio
        post.return_value = resp
        result = generate_novel_music(_novel(), ["mystery"], out, config, logger)

    assert result == out
    assert out.exists()
    assert out.read_bytes() == fake_audio
    meta = out.with_suffix(".json")
    assert meta.exists()
    assert "elevenlabs_music" in meta.read_text(encoding="utf-8")
    post.assert_called_once()
    call_kwargs = post.call_args
    assert call_kwargs.kwargs["json"]["force_instrumental"] is True


def test_generate_novel_sfx_writes_all_files(tmp_path: Path):
    config = AppConfig()
    config.elevenlabs_api_key = "test-key"
    logger = PipelineLogger(tmp_path / "logs")
    sfx_dir = tmp_path / "sfx"
    fake_audio = b"ID3" + b"\x00" * 1500

    def _fake_transcode(src: Path, dest: Path) -> None:
        dest.write_bytes(b"RIFF" + b"\x00" * 800)

    with (
        patch("src.novel_assets.elevenlabs_audio.requests.post") as post,
        patch("src.novel_assets.elevenlabs_audio._transcode_to_wav", side_effect=_fake_transcode),
    ):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = fake_audio
        post.return_value = resp
        result = generate_novel_sfx(_novel(), ["suspense"], sfx_dir, config, logger)

    assert result == sfx_dir
    assert novel_sfx_complete(sfx_dir)
    assert (sfx_dir / "sfx.json").exists()
    assert post.call_count == len(SFX_FILES)


def test_generate_skips_without_api_key(tmp_path: Path):
    config = AppConfig()
    config.elevenlabs_api_key = ""
    logger = PipelineLogger(tmp_path / "logs")
    assert generate_novel_music(_novel(), [], tmp_path / "bgm.mp3", config, logger) is None
    assert generate_novel_sfx(_novel(), [], tmp_path / "sfx", config, logger) is None


def test_manager_uses_cached_sfx_without_api(tmp_path: Path):
    config = AppConfig()
    config.elevenlabs_api_key = ""
    config.video.elevenlabs_audio_enabled = True
    data = tmp_path / "data"
    config.paths.data_dir = str(data)
    config.paths.db_path = str(data / "test.db")
    config.paths.stock_library = str(tmp_path / "assets" / "stock_library")
    logger = PipelineLogger(tmp_path / "logs")
    db = Database(config.path("db_path"))
    mgr = NovelAssetManager(config, logger, db)

    novel = _novel(7)
    novel_dir = mgr._novel_dir(novel)
    sfx_dir = novel_dir / "sfx"
    sfx_dir.mkdir(parents=True)
    for name in SFX_FILES.values():
        (sfx_dir / name).write_bytes(b"RIFF" + b"\x00" * 600)
    (sfx_dir / "sfx.json").write_text('{"source":"elevenlabs_sfx"}', encoding="utf-8")

    with patch("src.novel_assets.manager.fetch_novel_bgm", return_value=None):
        with patch("src.novel_assets.manager._generate_novel_pad") as pad:
            def _pad(path: Path, _novel: Novel) -> None:
                path.write_bytes(b"\x00" * 2000)
            pad.side_effect = _pad
            assets = mgr.ensure(novel, ["mystery"])

    assert assets.sfx_dir == sfx_dir
    assert novel_sfx_complete(assets.sfx_dir)


def test_manager_calls_elevenlabs_when_enabled(tmp_path: Path):
    config = AppConfig()
    config.elevenlabs_api_key = "test-key"
    config.video.elevenlabs_audio_enabled = True
    data = tmp_path / "data"
    config.paths.data_dir = str(data)
    config.paths.db_path = str(data / "test.db")
    config.paths.stock_library = str(tmp_path / "assets" / "stock_library")
    logger = PipelineLogger(tmp_path / "logs")
    db = Database(config.path("db_path"))
    mgr = NovelAssetManager(config, logger, db)
    novel = _novel(8)

    bgm_file = tmp_path / "bgm.mp3"
    bgm_file.write_bytes(b"\x00" * 2000)

    sfx_out = tmp_path / "fake_sfx"
    sfx_out.mkdir()
    for name in SFX_FILES.values():
        (sfx_out / name).write_bytes(b"RIFF" + b"\x00" * 600)

    with (
        patch(
            "src.novel_assets.manager.generate_novel_music",
            return_value=bgm_file,
        ) as music,
        patch(
            "src.novel_assets.manager.generate_novel_sfx",
            return_value=sfx_out,
        ) as sfx,
        patch.object(mgr.stock, "fetch_photo", return_value=None),
    ):
        assets = mgr.ensure(novel, ["storm", "sea"])

    music.assert_called_once()
    sfx.assert_called_once()
    assert assets.bgm_path == bgm_file
    assert assets.sfx_dir == sfx_out
