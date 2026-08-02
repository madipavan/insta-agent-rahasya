"""Pillow-based static post generator — carousel slides from script."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.brand.templates import BrandTemplates
from src.book_queue.models import EpisodeContext, ScriptOutput
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.static_post.splitter import split_into_slides_capped
from src.visuals.stock import StockResolver


class StaticPostGenerator:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.brand = BrandTemplates(config)
        self.stock = StockResolver(config, logger)

    def generate_all(
        self,
        context: EpisodeContext,
        script: ScriptOutput,
        output_dir: Path,
        stock_paths: list[Path] | None = None,
    ) -> list[Path]:
        """Generate one carousel image per script chunk."""
        output_dir.mkdir(parents=True, exist_ok=True)
        slides = self._build_slide_texts(script)
        self.logger.start("static_post", f"{len(slides)} carousel slides")

        paths: list[Path] = []
        for i, slide_text in enumerate(slides):
            stock_hint = (stock_paths[i % len(stock_paths)] if stock_paths else None)
            background = self._resolve_background(
                stock_hint, script.stock_keywords, i, len(slides)
            )
            img = self.brand.create_cinematic_quote_card(
                slide_text,
                self.config.static_post.width,
                self.config.static_post.height,
                background,
                slide_label=f"{i + 1}/{len(slides)}",
            )
            out = output_dir / f"static_post_{i + 1:02d}.png"
            img.save(out)
            paths.append(out)

        # Backward-compatible single file = first slide
        if paths:
            import shutil
            shutil.copy2(paths[0], output_dir / "static_post.png")

        self.logger.ok("static_post", f"{len(paths)} slides")
        return paths

    def generate(
        self,
        context: EpisodeContext,
        script: ScriptOutput,
        output_path: Path,
        stock_path: Path | None = None,
    ) -> Path:
        paths = self.generate_all(
            context,
            script,
            output_path.parent,
            [stock_path] if stock_path else None,
        )
        return paths[0] if paths else output_path

    def _build_slide_texts(self, script: ScriptOutput) -> list[str]:
        max_chars = self.config.static_post.chars_per_slide
        max_slides = self.config.static_post.max_slides
        source = script.carousel_source()
        if not source:
            source = script.static_post_text or script.hook
        slides = split_into_slides_capped(source, max_chars=max_chars, max_slides=max_slides)
        return slides or [script.static_post_text or script.hook or "..."]

    def _resolve_background(
        self,
        stock_path: Path | None,
        keywords: list[str],
        slide_index: int,
        total_slides: int,
    ) -> Image.Image | None:
        if stock_path and stock_path.suffix.lower() in (".mp4", ".mov", ".webm"):
            at_sec = 1.0 + (slide_index * 2.5)
            frame = self.stock.extract_video_frame(stock_path, at_sec=at_sec)
            if frame:
                return frame

        if stock_path and stock_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return Image.open(stock_path).convert("RGB")

        photo = self.stock.fetch_photo(
            keywords + ["cinematic", "artistic", f"scene{slide_index + 1}"],
            self.config.static_post.width,
            self.config.static_post.height,
        )
        return photo
