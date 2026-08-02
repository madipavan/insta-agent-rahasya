"""Render Hindi/Unicode captions as ASS subtitles for ffmpeg libass."""

from __future__ import annotations

import textwrap
from pathlib import Path

from src.visuals.captions import CaptionSegment


def _hindi_font_name() -> str:
  candidates = [
    ("assets/fonts/NotoSansDevanagari-Regular.ttf", "Noto Sans Devanagari"),
    ("C:/Windows/Fonts/mangal.ttf", "Mangal"),
    ("C:/Windows/Fonts/Nirmala.ttf", "Nirmala UI"),
    ("C:/Windows/Fonts/NotoSansDevanagari-Regular.ttf", "Noto Sans Devanagari"),
  ]
  for path, name in candidates:
    if Path(path).exists():
      return name
  return "Noto Sans Devanagari"


def _format_ass_time(seconds: float) -> str:
  seconds = max(0.0, seconds)
  hours = int(seconds // 3600)
  minutes = int((seconds % 3600) // 60)
  secs = seconds % 60
  return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _escape_ass(text: str) -> str:
  return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _wrap_text(text: str, width: int = 28) -> str:
  lines = textwrap.wrap(text, width=width)
  return "\\N".join(_escape_ass(line) for line in lines)


def write_ass_subtitles(
  segments: list[CaptionSegment],
  output_path: Path,
  *,
  width: int = 1080,
  height: int = 1920,
  font_size: int = 46,
) -> Path:
  font_name = _hindi_font_name()
  margin_v = int(height * 0.28)

  header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,3,1,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

  events: list[str] = []
  for seg in segments:
    if not seg.text.strip():
      continue
    start = _format_ass_time(seg.start)
    end = _format_ass_time(max(seg.end, seg.start + 0.5))
    text = _wrap_text(seg.text.strip())
    events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
  return output_path


def ass_filter_path(ass_path: Path) -> str:
  """Escape ASS path for ffmpeg subtitles filter."""
  fonts_dir = Path("assets/fonts")
  if not fonts_dir.exists():
    fonts_dir = Path("C:/Windows/Fonts")
  if not fonts_dir.exists():
    fonts_dir = ass_path.parent

  ass_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")
  fonts_escaped = str(fonts_dir.resolve()).replace("\\", "/").replace(":", "\\:")
  return f"subtitles='{ass_escaped}':fontsdir='{fonts_escaped}'"
