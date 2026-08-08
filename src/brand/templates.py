"""Shared brand templates for reels and static posts."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from src.config import AppConfig
from src.utils.hindi_text import hindi_font_paths, normalize_hindi_for_render

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


class BrandTemplates:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def _is_hindi(self, text: str) -> bool:
        return bool(_DEVANAGARI_RE.search(text))

    def _get_hindi_font(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for path in hindi_font_paths(self.config, bold=bold):
            if path.exists():
                return ImageFont.truetype(str(path), size)
        raise FileNotFoundError(
            "No Hindi font found. Run: bash scripts/download_fonts.sh"
        )

    def _get_font(self, font_path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            self.config.resolve_asset(font_path),
            Path(font_path),
            Path("C:/Windows/Fonts/georgiab.ttf"),
            Path("C:/Windows/Fonts/timesbd.ttf"),
        ]
        for path in candidates:
            if path.exists():
                return ImageFont.truetype(str(path), size)
        return ImageFont.load_default()

    def _get_caption_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Anek ExtraBold — same family as reel hook/caption overlays."""
        path = self.config.resolve_asset(self.config.brand.caption_font)
        if path.exists():
            return ImageFont.truetype(str(path), size)
        return self._get_hindi_font(size, bold=True)

    def _quote_font_for(
        self, text: str, size: int, *, bold: bool | None = None
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if self._is_hindi(text):
            use_bold = self.config.static_post.hindi_bold if bold is None else bold
            return self._get_hindi_font(size, bold=use_bold)
        return self._get_font(self.config.brand.quote_font, size)

    def create_card(
        self,
        text: str,
        width: int,
        height: int,
        subtitle: str = "",
        accent_line: bool = True,
    ) -> Image.Image:
        bg = self._hex_to_rgb(self.config.brand.bg_color)
        accent = self._hex_to_rgb(self.config.brand.accent_color)
        text_color = self._hex_to_rgb(self.config.brand.text_color)

        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)

        if accent_line:
            draw.rectangle([(0, height // 2 - 2), (width, height // 2 + 2)], fill=accent)

        display_font = self._get_font(self.config.brand.display_font, 72)
        body_font = self._get_font(self.config.brand.body_font, 36)

        self._draw_centered_text(draw, text, width, height // 2 - 80, display_font, text_color)
        if subtitle:
            self._draw_centered_text(draw, subtitle, width, height // 2 + 60, body_font, text_color)

        self._add_watermark(img)
        return img

    def create_cinematic_quote_card(
        self,
        quote: str,
        width: int,
        height: int,
        background: Image.Image | None = None,
        slide_label: str = "",
    ) -> Image.Image:
        """Moody quote post — cinematic background, centered text, bottom-left watermark."""
        quote = normalize_hindi_for_render(quote) if self._is_hindi(quote) else quote
        if background is not None:
            img = background.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
            img = ImageEnhance.Brightness(img).enhance(0.45)
            img = ImageEnhance.Contrast(img).enhance(1.15)
        else:
            img = Image.new("RGB", (width, height), self._hex_to_rgb(self.config.brand.bg_color))

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for y in range(height):
            alpha = int(120 + (y / height) * 100)
            overlay_draw.line([(0, y), (width, y)], fill=(0, 0, 0, min(alpha, 200)))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        draw = ImageDraw.Draw(img)
        sp = self.config.static_post
        font, wrapped, text_y = self._fit_quote_text(draw, quote, width, height)

        self._draw_centered_text(
            draw,
            wrapped,
            width,
            text_y,
            font,
            (245, 245, 245),
            stroke_width=sp.text_stroke_width,
        )

        watermark_font = self._get_font(self.config.brand.body_font, 28)
        watermark = self.config.brand.watermark_text
        draw.text((40, height - 70), watermark, font=watermark_font, fill=(230, 230, 230))

        if slide_label:
            label_font = self._get_font(self.config.brand.quote_font, 26)
            bbox = draw.textbbox((0, 0), slide_label, font=label_font)
            label_w = bbox[2] - bbox[0]
            draw.text(
                (width - label_w - 40, height - 70),
                slide_label,
                font=label_font,
                fill=(200, 200, 200),
            )

        return img

    def _fit_quote_text(
        self,
        draw: ImageDraw.ImageDraw,
        quote: str,
        width: int,
        height: int,
    ) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str, int]:
        sp = self.config.static_post
        max_text_height = int(height * sp.text_area_ratio)
        is_hindi = self._is_hindi(quote)
        max_lines = sp.max_lines_per_slide
        size_max = sp.quote_font_size_max
        size_min = sp.quote_font_size_min
        font_sizes = list(range(size_max, size_min - 1, -4))
        if not font_sizes:
            font_sizes = [size_max, size_min]
        wrap_widths = [18, 16, 14, 12, 10] if is_hindi else [28, 24, 22, 20, 18]

        for font_size in font_sizes:
            font = self._quote_font_for(quote, font_size)
            for wrap_w in wrap_widths:
                wrapped = textwrap.fill(quote, width=wrap_w)
                bbox = draw.multiline_textbbox(
                    (0, 0), wrapped, font=font, align="center", spacing=14,
                )
                text_h = bbox[3] - bbox[1]
                line_count = wrapped.count("\n") + 1
                if text_h <= max_text_height and line_count <= max_lines:
                    y = (height - text_h) // 2 - 30
                    return font, wrapped, max(100, y)

        font = self._quote_font_for(quote, size_min)
        wrapped = textwrap.fill(quote, width=12 if is_hindi else 20)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, align="center", spacing=12)
        text_h = bbox[3] - bbox[1]
        return font, wrapped, max(100, (height - text_h) // 2 - 30)

    def create_intro_card(self, width: int, height: int) -> Image.Image:
        return self.create_card(
            self.config.brand.watermark_text,
            width,
            height,
            subtitle="Foreign thrillers Bollywood forgot",
        )

    def create_gradient_fallback(self, width: int, height: int) -> Image.Image:
        """Dark cinematic gradient when no stock photo is available."""
        bg = self._hex_to_rgb(self.config.brand.bg_color)
        accent = self._hex_to_rgb(self.config.brand.accent_color)
        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)
        for y in range(height):
            blend = y / height
            r = int(bg[0] * (1 - blend) + accent[0] * blend * 0.3)
            g = int(bg[1] * (1 - blend) + accent[1] * blend * 0.3)
            b = int(bg[2] * (1 - blend) + accent[2] * blend * 0.3)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        return img

    def create_novel_thumbnail_from_photo(
        self,
        photo: Image.Image,
        width: int,
        height: int,
    ) -> Image.Image:
        """Artistic stock photo base — reused every episode for this novel."""
        img = photo.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
        img = ImageEnhance.Brightness(img).enhance(0.55)
        img = ImageEnhance.Contrast(img).enhance(1.1)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for y in range(height):
            alpha = int(40 + (y / height) * 80)
            od.line([(0, y), (width, y)], fill=(0, 0, 0, min(alpha, 140)))
        return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    def create_novel_thumbnail_base(
        self,
        novel_title: str,
        author: str,
        width: int,
        height: int,
    ) -> Image.Image:
        """Novel cover template — same design reused every episode."""
        bg = self._hex_to_rgb(self.config.brand.bg_color)
        accent = self._hex_to_rgb(self.config.brand.accent_color)
        text_color = self._hex_to_rgb(self.config.brand.text_color)

        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)

        draw.rectangle([(80, height // 2 - 4), (width - 80, height // 2 + 4)], fill=accent)

        title_font = self._get_font(self.config.brand.display_font, 88)
        author_font = self._get_font(self.config.brand.body_font, 40)
        brand_font = self._get_font(self.config.brand.body_font, 36)

        self._draw_centered_text(draw, novel_title.upper(), width, height // 2 - 200, title_font, text_color)
        self._draw_centered_text(draw, author, width, height // 2 + 40, author_font, text_color)
        self._draw_centered_text(
            draw, self.config.brand.watermark_text, width, height - 180, brand_font, accent
        )
        return img

    def create_episode_thumbnail(
        self,
        novel_title: str,
        episode_num: int,
        total_episodes: int,
        base_image_path: Path | None,
        width: int,
        height: int,
        hook_text: str = "",
    ) -> Image.Image:
        """Episode cover — Bebas EP number + optional Hindi hook in Anek."""
        if base_image_path and base_image_path.exists():
            img = Image.open(base_image_path).convert("RGB").resize((width, height))
        else:
            img = self.create_gradient_fallback(width, height)

        accent = self._hex_to_rgb(self.config.brand.accent_color)
        text_color = self._hex_to_rgb(self.config.brand.text_color)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (width, height)], fill=(0, 0, 0, 60))
        band_top = height // 2 - 160
        band_bottom = height // 2 + 160
        od.rectangle([(0, band_top), (width, band_bottom)], fill=(10, 14, 26, 140))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        ep_font = self._get_font(self.config.brand.display_font, 220)
        ep_text = f"EP {episode_num}"

        ep_bbox = draw.textbbox((0, 0), ep_text, font=ep_font)
        ep_w = ep_bbox[2] - ep_bbox[0]
        ep_h = ep_bbox[3] - ep_bbox[1]
        ep_x = (width - ep_w) // 2
        ep_y = height // 2 - ep_h // 2
        draw.text(
            (ep_x, ep_y),
            ep_text,
            font=ep_font,
            fill=accent,
            stroke_width=5,
            stroke_fill=(0, 0, 0),
        )

        hook = normalize_hindi_for_render((hook_text or "").strip()) if hook_text else ""
        if hook:
            hook_font = self._get_caption_font(52)
            wrapped = textwrap.fill(hook, width=22)
            hook_bbox = draw.multiline_textbbox(
                (0, 0), wrapped, font=hook_font, align="center", spacing=8
            )
            hook_w = hook_bbox[2] - hook_bbox[0]
            hook_h = hook_bbox[3] - hook_bbox[1]
            hook_x = (width - hook_w) // 2
            hook_y = min(height - hook_h - 120, band_bottom + 24)
            draw.multiline_text(
                (hook_x, hook_y),
                wrapped,
                font=hook_font,
                fill=text_color,
                align="center",
                spacing=8,
                stroke_width=3,
                stroke_fill=(0, 0, 0),
            )

        return img

    def create_outro_card(self, width: int, height: int, next_part: int) -> Image.Image:
        return self.create_card(
            f"Follow for Part {next_part}",
            width,
            height,
            subtitle=self.config.brand.watermark_text,
        )

    def _draw_centered_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        width: int,
        y: int,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        color: tuple[int, int, int],
        stroke_width: int = 3,
    ) -> None:
        bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=14)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        draw.multiline_text(
            (x, y),
            text,
            font=font,
            fill=color,
            align="center",
            spacing=14,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0) if stroke_width > 0 else None,
        )

    def _add_watermark(self, img: Image.Image) -> None:
        draw = ImageDraw.Draw(img)
        font = self._get_font(self.config.brand.body_font, 24)
        text = self.config.brand.watermark_text
        color = self._hex_to_rgb(self.config.brand.accent_color)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = img.width - text_width - 20
        y = img.height - 40
        draw.text((x, y), text, font=font, fill=color)

        logo_path = self.config.resolve_asset(self.config.brand.logo_path)
        if logo_path.exists():
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((80, 80))
            img.paste(logo, (20, img.height - 90), logo)

    def save_card(self, img: Image.Image, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        return path
