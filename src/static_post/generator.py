"""Pillow-based static post generator — carousel slides from script."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.brand.templates import BrandTemplates
from src.book_queue.models import EpisodeContext, ScriptOutput
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.static_post.splitter import split_into_slides_capped
from src.visuals.bilingual import bilingual_slide_texts, split_parallel
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
        still_pool = list(stock_paths or [])
        use_panels = bool(
            still_pool
            and all(p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") for p in still_pool)
            and getattr(self.config, "content_mode", "") == "indian_dark_serial"
            and script.panels
        )
        if use_panels:
            for i, panel_path in enumerate(still_pool[: self.config.static_post.max_slides]):
                img = Image.open(panel_path).convert("RGB")
                img = self._fit_carousel(img)
                out = output_dir / f"static_post_{i + 1:02d}.png"
                img.save(out)
                paths.append(out)
        else:
            for i, slide_text in enumerate(slides):
                stock_hint = (stock_paths[i % len(stock_paths)] if stock_paths else None)
                background = self._resolve_background(
                    stock_hint,
                    script.stock_keywords,
                    i,
                    len(slides),
                    still_pool=still_pool,
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
        # Carousel must mirror the full reel voiceover, not the short static_post_text blurb.
        source = (script.episode_only_script or script.voiceover_script or "").strip()
        if not source:
            source = (script.static_post_text or script.hook or "").strip()
        slides = split_into_slides_capped(source, max_chars=max_chars, max_slides=max_slides)
        if not slides:
            slides = [script.static_post_text or script.hook or "..."]

        english = (script.english_voiceover or "").strip()
        if english and slides:
            # Slightly shorter English chunks so dual-language slides stay compact
            en_chars = max(60, int(max_chars * 0.85))
            en_slides = split_into_slides_capped(english, max_chars=en_chars, max_slides=max_slides)
            if len(en_slides) != len(slides):
                en_slides = split_parallel(english, len(slides))
            slides = bilingual_slide_texts(slides, en_slides)

        if slides:
            self.logger.info(
                f"static_post | {len(source)} chars → {len(slides)} slides "
                f"(max {max_slides}, ~{max_chars} chars/slide, bilingual={bool(english)})"
            )
        return slides

    def _resolve_background(
        self,
        stock_path: Path | None,
        keywords: list[str],
        slide_index: int,
        total_slides: int,
        *,
        still_pool: list[Path] | None = None,
    ) -> Image.Image | None:
        art_cfg = getattr(self.config, "replicate_art", None)
        static_use_rep = bool(getattr(art_cfg, "static_use_replicate", True))

        # Prefer cycling through reel Replicate stills (no extra API cost)
        pool = still_pool or []
        image_pool = [
            p
            for p in pool
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and p.exists()
        ]
        if image_pool:
            chosen = image_pool[slide_index % len(image_pool)]
            return Image.open(chosen).convert("RGB")

        if static_use_rep:
            photo = self.stock.fetch_photo(
                keywords + ["cinematic", "artistic", f"scene{slide_index + 1}"],
                self.config.static_post.width,
                self.config.static_post.height,
            )
            if photo:
                return photo

        if stock_path and stock_path.suffix.lower() in (".mp4", ".mov", ".webm"):
            at_sec = 1.0 + (slide_index * 2.5)
            frame = self.stock.extract_video_frame(stock_path, at_sec=at_sec)
            if frame:
                return frame

        if stock_path and stock_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return Image.open(stock_path).convert("RGB")

        return self.stock.fetch_photo(
            keywords + ["cinematic", "artistic", f"scene{slide_index + 1}"],
            self.config.static_post.width,
            self.config.static_post.height,
        )

    def _fit_carousel(self, img: Image.Image) -> Image.Image:
        target_w = self.config.static_post.width
        target_h = self.config.static_post.height
        src = img.convert("RGB")
        src_ratio = src.width / src.height
        target_ratio = target_w / target_h
        if src_ratio > target_ratio:
            new_h = target_h
            new_w = int(new_h * src_ratio)
        else:
            new_w = target_w
            new_h = int(new_w / src_ratio)
        resized = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = max(0, (new_w - target_w) // 2)
        top = max(0, (new_h - target_h) // 2)
        return resized.crop((left, top, left + target_w, top + target_h))
