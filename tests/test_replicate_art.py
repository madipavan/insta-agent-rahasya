"""Tests for Replicate fictional art prompts and stock photo fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import AppConfig, ReplicateArtConfig
from src.visuals.replicate_art import (
    ReplicateArtClient,
    build_fiction_prompt,
    prompt_looks_fictional,
)
from src.visuals.stock import StockResolver


def test_build_fiction_prompt_includes_novel_and_avoids_photo():
    prompt = build_fiction_prompt(
        ["foggy marsh", "sealed letter", "cinematic"],
        novel_title="The Riddle of the Sands",
        style_tag="stylized cinematic illustration, fictional thriller book-art",
        negative_avoid="photorealistic, real photo, stock photo",
    )
    assert prompt_looks_fictional(prompt)
    assert 'classic novel "The Riddle of the Sands"' in prompt
    assert "foggy marsh" in prompt
    assert "not a real photograph" in prompt
    assert "avoid:" in prompt
    assert "photorealistic" in prompt


def test_build_fiction_prompt_without_title():
    prompt = build_fiction_prompt(["shadowed staircase", "oil lamp"])
    assert "fictional illustrated scene" in prompt
    assert "not a real photograph" in prompt
    assert prompt_looks_fictional(prompt)


def test_replicate_generate_photo_success(tmp_path: Path):
    config = AppConfig()
    config.replicate_art = ReplicateArtConfig(enabled=True)
    config.replicate_api_token = "r8_test"
    logger = MagicMock()
    client = ReplicateArtClient(config, logger, tmp_path)

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with patch.object(client, "_run_model", return_value=png_bytes):
        path = client.generate_photo(
            ["foggy marsh", "yacht"],
            width=1080,
            height=1920,
            novel_title="The Riddle of the Sands",
        )

    assert path is not None
    assert path.exists()
    assert path.stat().st_size > 0
    # Cache hit on second call
    with patch.object(client, "_run_model") as run_mock:
        again = client.generate_photo(
            ["foggy marsh", "yacht"],
            width=1080,
            height=1920,
            novel_title="The Riddle of the Sands",
        )
        run_mock.assert_not_called()
    assert again == path


def test_replicate_generate_photo_failure_returns_none(tmp_path: Path):
    config = AppConfig()
    config.replicate_art = ReplicateArtConfig(enabled=True)
    config.replicate_api_token = "r8_test"
    logger = MagicMock()
    client = ReplicateArtClient(config, logger, tmp_path)

    with patch.object(client, "_run_model", side_effect=RuntimeError("billing required")):
        assert client.generate_photo(["fog"]) is None
    logger.warn.assert_called()


def test_fetch_photo_falls_back_to_stock(tmp_path: Path):
    config = AppConfig()
    config.replicate_art = ReplicateArtConfig(enabled=True)
    config.replicate_api_token = "r8_test"
    config.paths.output_dir = str(tmp_path)
    logger = MagicMock()
    stock = StockResolver(config, logger)

    stock_jpg = tmp_path / "stock.jpg"
    from PIL import Image

    Image.new("RGB", (64, 64), "#123456").save(stock_jpg)

    with patch.object(stock.replicate, "generate_photo", return_value=None):
        with patch.object(stock, "_fetch_remote_photo", return_value=stock_jpg):
            img = stock.fetch_photo(["mystery hallway"], 1080, 1920, novel_title="Test")

    assert img is not None
    assert img.size == (64, 64)


def test_fetch_photo_prefers_replicate(tmp_path: Path):
    config = AppConfig()
    config.replicate_art = ReplicateArtConfig(enabled=True)
    config.replicate_api_token = "r8_test"
    config.paths.output_dir = str(tmp_path)
    logger = MagicMock()
    stock = StockResolver(config, logger)

    art = tmp_path / "art.png"
    from PIL import Image

    Image.new("RGB", (32, 48), "#abcdef").save(art)

    with patch.object(stock.replicate, "generate_photo", return_value=art) as gen:
        with patch.object(stock, "_fetch_remote_photo") as stock_fetch:
            img = stock.fetch_photo(["sealed letter"], 1080, 1920, novel_title="Woman in White")

    gen.assert_called_once()
    stock_fetch.assert_not_called()
    assert img is not None
    assert img.size == (32, 48)


def test_resolve_visuals_stills_only_skips_stock_video(tmp_path: Path):
    from PIL import Image

    config = AppConfig()
    config.replicate_art = ReplicateArtConfig(
        enabled=True, prefer_stills_only=True, reel_still_count=4
    )
    config.replicate_api_token = "r8_test"
    config.paths.output_dir = str(tmp_path)
    logger = MagicMock()
    stock = StockResolver(config, logger)

    paths = []
    for i in range(4):
        p = tmp_path / f"still_{i}.png"
        Image.new("RGB", (8, 8), (i * 40, 10, 10)).save(p)
        paths.append(p)

    def fake_gen(keywords, **kwargs):
        # Return distinct path per scene index in keywords
        for k in keywords:
            if k.startswith("scene"):
                idx = int(k.replace("scene", "")) - 1
                return paths[idx % len(paths)]
        return paths[0]

    with patch.object(stock.replicate, "generate_photo", side_effect=fake_gen):
        with patch.object(stock, "_fetch_remote_videos") as vids:
            with patch.object(stock, "_find_local", return_value=None):
                result = stock.resolve_visuals(["foggy marsh", "yacht"], tmp_path)

    vids.assert_not_called()
    assert len(result) == 4
    assert all(p.suffix == ".png" for p in result)


def test_static_background_reuses_reel_stills(tmp_path: Path):
    from PIL import Image

    from src.static_post.generator import StaticPostGenerator

    config = AppConfig()
    config.replicate_art = ReplicateArtConfig(enabled=True, static_use_replicate=True)
    config.replicate_api_token = "r8_test"
    logger = MagicMock()
    gen = StaticPostGenerator(config, logger)

    stills = []
    for i in range(3):
        p = tmp_path / f"r{i}.png"
        Image.new("RGB", (16, 16), (i * 50, 0, 0)).save(p)
        stills.append(p)

    with patch.object(gen.stock, "fetch_photo") as fetch:
        bg0 = gen._resolve_background(None, ["kw"], 0, 3, still_pool=stills)
        bg1 = gen._resolve_background(None, ["kw"], 1, 3, still_pool=stills)
        bg2 = gen._resolve_background(None, ["kw"], 2, 3, still_pool=stills)

    fetch.assert_not_called()
    assert bg0 is not None and bg1 is not None and bg2 is not None
    assert bg0.getpixel((0, 0))[0] == 0
    assert bg1.getpixel((0, 0))[0] == 50
    assert bg2.getpixel((0, 0))[0] == 100
