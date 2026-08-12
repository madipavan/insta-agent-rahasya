"""Render Hindi/Unicode captions as ASS subtitles for ffmpeg libass."""

from __future__ import annotations

import textwrap
from pathlib import Path

from src.config import AppConfig, ROOT_DIR
from src.utils.hindi_text import hindi_font_paths, normalize_hindi_for_render
from src.visuals.captions import CaptionSegment

_ASS_FAMILY_NAMES = {
    "AnekDevanagari-ExtraBold.ttf": "Anek Devanagari ExtraBold",
    "AnekDevanagari-Bold.ttf": "Anek Devanagari",
    "TiroDevanagariHindi-Regular.ttf": "Tiro Devanagari Hindi",
    "NotoSansDevanagari-Bold.ttf": "Noto Sans Devanagari",
    "NotoSansDevanagari-Regular.ttf": "Noto Sans Devanagari",
    "Inter-Regular.ttf": "Inter",
}


def _font_family_from_path(font_path: Path) -> str:
    if font_path.name in _ASS_FAMILY_NAMES:
        return _ASS_FAMILY_NAMES[font_path.name]
    stem = font_path.stem.replace("-", " ")
    return stem


def _resolve_caption_font(config: AppConfig) -> tuple[Path, str]:
    for path in hindi_font_paths(config, bold=True):
        if path.exists():
            return path, _font_family_from_path(path)
    fallback = config.resolve_asset(config.brand.caption_font)
    return fallback, "Anek Devanagari ExtraBold"


def _resolve_english_font(config: AppConfig) -> str:
    body = config.resolve_asset(config.brand.body_font)
    if body.exists():
        return _font_family_from_path(body)
    return "Inter"


def _format_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _wrap_line(text: str, width: int) -> str:
    lines = textwrap.wrap(text, width=width) or [text]
    return "\\N".join(_escape_ass(line) for line in lines)


def _format_bilingual_event(
    text: str,
    *,
    hindi_size: int,
    english_size: int,
    english_font: str,
    wrap_hi: int = 26,
    wrap_en: int = 34,
) -> str:
    """Hindi (primary size) + English (smaller) as stacked ASS lines."""
    parts = [p.strip() for p in (text or "").split("\n") if p.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return _wrap_line(parts[0], wrap_hi)

    hi = _wrap_line(parts[0], wrap_hi)
    en_raw = " ".join(parts[1:])
    en = _wrap_line(en_raw, wrap_en)
    # Inline override: smaller English under Hindi
    return (
        f"{{\\fs{hindi_size}}}{hi}"
        f"{{\\r}}\\N{{\\fn{english_font}\\fs{english_size}\\b0}}{en}"
    )


def write_ass_subtitles(
    segments: list[CaptionSegment],
    output_path: Path,
    config: AppConfig,
    *,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    font_path, font_name = _resolve_caption_font(config)
    font_size = config.brand.caption_font_size
    hook_size = config.brand.hook_font_size
    en_size = getattr(config.brand, "english_caption_font_size", 28) or 28
    outline = config.brand.caption_outline
    margin_v = int(height * 0.26)
    accent_bgr = "&H003A1EC4"  # #C41E3A
    english_font = _resolve_english_font(config)
    _ = font_path  # fontsdir resolved by ass_filter_path

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{outline},1,2,60,60,{margin_v},1
Style: Hook,{font_name},{hook_size},{accent_bgr},&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{outline + 1},2,2,60,60,{margin_v + 16},1
Style: English,{english_font},{en_size},&H00DDDDDD,&H000000FF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,{max(2, outline - 1)},1,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    for seg in segments:
        raw = normalize_hindi_for_render(seg.text.strip())
        if not raw:
            continue
        start = _format_ass_time(seg.start)
        end = _format_ass_time(max(seg.end, seg.start + 0.5))
        style = seg.style if seg.style in ("Default", "Hook") else "Default"
        hi_size = hook_size if style == "Hook" else font_size
        text = _format_bilingual_event(
            raw,
            hindi_size=hi_size,
            english_size=en_size,
            english_font=english_font,
        )
        events.append(f"Dialogue: 0,{start},{end},{style},,0,0,0,,{text}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
    return output_path


def ass_filter_path(ass_path: Path, config: AppConfig | None = None) -> str:
    """Escape ASS path for ffmpeg subtitles filter."""
    fonts_dir = ROOT_DIR / "assets/fonts"
    if config is not None:
        caption_font = config.resolve_asset(config.brand.caption_font)
        if caption_font.parent.exists():
            fonts_dir = caption_font.parent
    if not fonts_dir.exists():
        fonts_dir = Path("C:/Windows/Fonts")
    if not fonts_dir.exists():
        fonts_dir = ass_path.parent

    ass_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
    fonts_escaped = str(fonts_dir.resolve()).replace("\\", "/").replace(":", "\\:")
    return f"subtitles='{ass_escaped}':fontsdir='{fonts_escaped}'"
