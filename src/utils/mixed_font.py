"""PIL helpers: draw Hinglish with Devanagari + Latin fallback fonts."""

from __future__ import annotations

from PIL import ImageDraw, ImageFont

from src.utils.hindi_text import contains_devanagari, iter_script_runs

FontT = ImageFont.FreeTypeFont | ImageFont.ImageFont


def _advance(font: FontT, text: str) -> float:
    if not text:
        return 0.0
    getlength = getattr(font, "getlength", None)
    if callable(getlength):
        return float(getlength(text))
    bbox = font.getbbox(text) if hasattr(font, "getbbox") else (0, 0, 0, 0)
    return float(bbox[2] - bbox[0])


def _font_for_run(kind: str, primary: FontT, latin: FontT | None) -> FontT:
    if kind == "latin" and latin is not None:
        return latin
    return primary


def line_width(text: str, primary: FontT, latin: FontT | None) -> float:
    if not text:
        return 0.0
    if latin is None or not contains_devanagari(text):
        return _advance(primary, text)
    return sum(
        _advance(_font_for_run(kind, primary, latin), run)
        for kind, run in iter_script_runs(text)
    )


def line_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    primary: FontT,
    latin: FontT | None,
) -> tuple[int, int, int, int]:
    """Tight bbox for a single line at origin (0, 0)."""
    if not text:
        return (0, 0, 0, 0)
    if latin is None or not contains_devanagari(text):
        return draw.textbbox((0, 0), text, font=primary)

    x = 0.0
    top = 0
    bottom = 0
    left = 0
    first = True
    for kind, run in iter_script_runs(text):
        font = _font_for_run(kind, primary, latin)
        bbox = draw.textbbox((int(round(x)), 0), run, font=font)
        if first:
            left = bbox[0]
            top = bbox[1]
            bottom = bbox[3]
            first = False
        else:
            left = min(left, bbox[0])
            top = min(top, bbox[1])
            bottom = max(bottom, bbox[3])
        x += _advance(font, run)
    right = int(round(x))
    return (left, top, max(right, left), bottom)


def multiline_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    primary: FontT,
    latin: FontT | None,
    *,
    spacing: int = 14,
) -> tuple[int, int, int, int]:
    lines = (text or "").split("\n")
    if not lines:
        return (0, 0, 0, 0)
    y = 0
    left = 0
    right = 0
    top = 0
    bottom = 0
    first = True
    for i, line in enumerate(lines):
        bbox = line_bbox(draw, line, primary, latin)
        line_h = bbox[3] - bbox[1]
        if first:
            left, top, right, bottom = bbox[0], bbox[1], bbox[2], bbox[3]
            first = False
        else:
            left = min(left, bbox[0])
            right = max(right, bbox[2])
            bottom = max(bottom, y + bbox[3])
        y += line_h + (spacing if i < len(lines) - 1 else 0)
    if first:
        return (0, 0, 0, 0)
    # Normalize so height reflects stacked lines from y=0 content top
    return (left, top, right, bottom)


def draw_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    primary: FontT,
    latin: FontT | None,
    *,
    fill: tuple[int, int, int],
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] | None = None,
) -> None:
    x, y = xy
    if latin is None or not contains_devanagari(text):
        draw.text(
            (x, y),
            text,
            font=primary,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        return
    cursor = float(x)
    for kind, run in iter_script_runs(text):
        font = _font_for_run(kind, primary, latin)
        draw.text(
            (cursor, y),
            run,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        cursor += _advance(font, run)


def draw_multiline_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    y: int,
    primary: FontT,
    latin: FontT | None,
    *,
    fill: tuple[int, int, int],
    spacing: int = 14,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] | None = None,
) -> int:
    """Draw centered multiline mixed text; return bottom y after last line."""
    lines = (text or "").split("\n")
    cy = float(y)
    for i, line in enumerate(lines):
        bbox = line_bbox(draw, line, primary, latin)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x = (width - line_w) // 2 - bbox[0]
        draw_line(
            draw,
            (x, cy),
            line,
            primary,
            latin,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        cy += line_h
        if i < len(lines) - 1:
            cy += spacing
    return int(round(cy))
