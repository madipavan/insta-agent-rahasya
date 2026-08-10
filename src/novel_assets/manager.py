"""Assign and cache per-novel BGM and thumbnail base art."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.book_queue.models import Novel
from src.book_queue.store import Database
from src.brand.templates import BrandTemplates
from src.config import AppConfig
from src.novel_assets.bgm import (
    _build_search_query,
    _generate_novel_pad,
    _write_meta,
    fetch_novel_bgm,
    is_synthetic_bgm,
)
from src.pipeline.logger import PipelineLogger
from src.visuals.stock import StockResolver


@dataclass
class NovelAssets:
    novel_dir: Path
    bgm_path: Path | None
    thumbnail_base: Path


class NovelAssetManager:
    def __init__(
        self,
        config: AppConfig,
        logger: PipelineLogger,
        db: Database,
        stock: StockResolver | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.db = db
        self.stock = stock or StockResolver(config, logger)
        self.brand = BrandTemplates(config)
        self.bgm_library = config.path("stock_library").parent / "bgm_library"
        self.bgm_library.mkdir(parents=True, exist_ok=True)
        self.novels_root = config.path("data_dir") / "novels"
        self.novels_root.mkdir(parents=True, exist_ok=True)

    def ensure(self, novel: Novel, keywords: list[str] | None = None) -> NovelAssets:
        novel_dir = self._novel_dir(novel)
        novel_dir.mkdir(parents=True, exist_ok=True)
        kw = keywords or []

        bgm_path = self._ensure_bgm(novel, novel_dir, kw)
        thumbnail_base = self._ensure_thumbnail_base(novel, novel_dir, kw)

        self.db.set_novel_assets(novel.id, str(bgm_path) if bgm_path else "", str(thumbnail_base))
        return NovelAssets(novel_dir=novel_dir, bgm_path=bgm_path, thumbnail_base=thumbnail_base)

    def episode_thumbnail(
        self,
        novel: Novel,
        episode_num: int,
        total_episodes: int,
        output_path: Path,
        assets: NovelAssets | None = None,
        hook_text: str = "",
    ) -> Path:
        assets = assets or self.ensure(novel)
        img = self.brand.create_episode_thumbnail(
            novel_title=novel.title,
            episode_num=episode_num,
            total_episodes=total_episodes,
            base_image_path=assets.thumbnail_base,
            width=self.config.video.width,
            height=self.config.video.height,
            hook_text=hook_text,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)
        return output_path

    def _novel_dir(self, novel: Novel) -> Path:
        slug = self._slugify(novel.title)
        return self.novels_root / f"{novel.id}_{slug}"

    def _ensure_bgm(self, novel: Novel, novel_dir: Path, keywords: list[str]) -> Path | None:
        cached = novel_dir / "bgm.mp3"
        meta = novel_dir / "bgm.json"

        if cached.exists():
            if meta.exists() and not is_synthetic_bgm(cached):
                return cached
            if meta.exists() and is_synthetic_bgm(cached):
                # Keep generated pad — CI often cannot reach YouTube every run.
                self.logger.info(f"Using synthetic BGM pad for '{novel.title}'")
                return cached
            if cached.stat().st_size > 900_000:
                return cached

        result = fetch_novel_bgm(
            novel, keywords, cached, self.logger, library_dir=self.bgm_library
        )
        if result and result.exists():
            self.logger.info(f"Assigned BGM for '{novel.title}'")
            return result

        try:
            query = _build_search_query(novel, keywords)
            _generate_novel_pad(cached, novel)
            _write_meta(cached, novel, query, source="synthetic")
            self.logger.warn(
                "novel_assets",
                f"BGM download failed — generated synthetic pad for '{novel.title}'",
            )
            return cached
        except (OSError, subprocess.CalledProcessError) as exc:
            self.logger.warn("novel_assets", f"BGM unavailable for '{novel.title}': {exc}")
            return None

    def _ensure_thumbnail_base(
        self, novel: Novel, novel_dir: Path, keywords: list[str]
    ) -> Path:
        cached = novel_dir / "thumbnail_art.png"
        if cached.exists():
            return cached

        stored = self.db.get_novel_thumbnail_base(novel.id)
        if stored and Path(stored).exists() and Path(stored).name == "thumbnail_art.png":
            shutil.copy2(stored, cached)
            return cached

        thumb_keywords = self._thumbnail_keywords(novel, keywords)
        photo = self.stock.fetch_photo(
            thumb_keywords, self.config.video.width, self.config.video.height
        )

        if photo:
            img = self.brand.create_novel_thumbnail_from_photo(
                photo,
                width=self.config.video.width,
                height=self.config.video.height,
            )
            self.logger.info(f"Fetched artistic thumbnail for '{novel.title}'")
        else:
            img = self.brand.create_novel_thumbnail_from_photo(
                self.brand.create_gradient_fallback(
                    self.config.video.width, self.config.video.height
                ),
                width=self.config.video.width,
                height=self.config.video.height,
            )
            self.logger.warn(
                "novel_assets", f"No stock photo for '{novel.title}' — using gradient fallback"
            )

        img.save(cached)
        return cached

    def _thumbnail_keywords(self, novel: Novel, keywords: list[str]) -> list[str]:
        title_words = [w for w in novel.title.split() if len(w) > 3][:3]
        base = keywords[:3] if keywords else ["mystery", "thriller", "dark"]
        return title_words + base + ["cinematic", "artistic", "moody", "noir"]

    def _slugify(self, text: str) -> str:
        import re
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return slug[:40] or "novel"
