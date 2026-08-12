"""Tests for Hindi tofu / dual-font script runs."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from src.config import load_config
from src.utils.hindi_text import (
    iter_script_runs,
    normalize_hindi_for_render,
    resolve_latin_font_path,
)
from src.utils import mixed_font
from src.visuals.caption_renderer import _ass_mixed_line


def test_normalize_ellipsis_and_quotes() -> None:
    raw = "हैं… 'trap' — ok"
    out = normalize_hindi_for_render(raw)
    assert "…" not in out
    assert "..." in out
    assert "'" in out
    assert "—" not in out


def test_iter_script_runs_splits_names_and_punct() -> None:
    text = normalize_hindi_for_render("Soho की गलियों में Verloc… trap?")
    runs = iter_script_runs(text)
    kinds = [k for k, _ in runs]
    joined = {k: "".join(r for kk, r in runs if kk == k) for k in ("deva", "latin")}
    assert "latin" in kinds and "deva" in kinds
    assert "Soho" in joined["latin"]
    assert "Verloc" in joined["latin"]
    assert "trap" in joined["latin"]
    assert "..." in joined["latin"] or "." in joined["latin"]
    assert "की" in joined["deva"]


def test_mixed_font_line_renders_latin_without_tofu_mask() -> None:
    config = load_config()
    latin_path = resolve_latin_font_path(config)
    assert latin_path is not None
    # Prefer Devanagari-only face to prove fallback is required
    from src.utils.hindi_text import resolve_hindi_font_path

    hi_path = resolve_hindi_font_path(config, bold=True)
    assert hi_path is not None

    size = 48
    hi_font = ImageFont.truetype(str(hi_path), size)
    latin_font = ImageFont.truetype(str(latin_path), size)

    # Pure Devanagari font: Latin letter masks are identical (.notdef)
    s_mask = bytes(hi_font.getmask("S"))
    o_mask = bytes(hi_font.getmask("o"))
    assert s_mask == o_mask

    img = Image.new("RGB", (800, 120), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    mixed_font.draw_line(
        draw,
        (20, 30),
        "Soho Verloc trap...",
        hi_font,
        latin_font,
        fill=(255, 255, 255),
    )
    # Sample a few pixels that should be ink from Latin glyphs (not empty)
    # Full black canvas except text — any bright pixel means glyphs drew
    extrema = img.convert("L").getextrema()
    assert extrema[1] > 200


def test_ass_mixed_line_injects_latin_font_tags() -> None:
    line = normalize_hindi_for_render("Soho की गलियों")
    out = _ass_mixed_line(line, hindi_font="Anek Devanagari ExtraBold", latin_font="Arial")
    assert "\\fnArial" in out
    assert "Soho" in out
    assert "की" in out
