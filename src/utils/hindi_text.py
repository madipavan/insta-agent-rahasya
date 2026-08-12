"""Normalize Hindi text for PIL / ASS rendering (Devanagari fonts lack some symbols)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from src.config import AppConfig, ROOT_DIR

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

ScriptKind = Literal["deva", "latin"]

# Symbols LLMs often emit that Devanagari TTFs do not include → tofu squares.
# Even after ASCII substitution, Latin/punctuation still need a Latin-capable font
# (Noto/Anek Devanagari ship .notdef for A–Z, digits, ., ?, …).
_CHAR_REPLACEMENTS = str.maketrans(
    {
        "\u2026": "...",  # …
        "\u2022": "-",  # •
        "\u00b7": "-",  # ·
        "\u2014": "-",  # —
        "\u2013": "-",  # –
        "\u2018": "'",  # '
        "\u2019": "'",  # '
        "\u201c": '"',  # "
        "\u201d": '"',  # "
        "\u00a0": " ",
        "\u2044": "/",
        "\u2212": "-",
        "\uff0e": ".",  # fullwidth full stop
        "\uff1f": "?",  # fullwidth question
        "\uff01": "!",  # fullwidth exclamation
    }
)

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U0001F600-\U0001F64F"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")


def normalize_hindi_for_render(text: str) -> str:
    """Replace punctuation/emoji missing from Devanagari fonts before draw."""
    if not text:
        return ""
    text = text.translate(_CHAR_REPLACEMENTS)
    text = _EMOJI_RE.sub("", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    return re.sub(r" +", " ", text).strip()


def sanitize_hindi_text(text: str) -> str:
    """Keep Devanagari + safe ASCII punctuation for carousel slides."""
    text = normalize_hindi_for_render(text)
    cleaned: list[str] = []
    for ch in text:
        if _DEVANAGARI_RE.match(ch):
            cleaned.append(ch)
        elif ch.isascii() and (ch.isalnum() or ch in " .,!?-'\"()"):
            cleaned.append(ch)
        elif ch in "।॥":
            cleaned.append(ch)
        elif ch.isspace():
            cleaned.append(" ")
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def _char_script_kind(ch: str) -> ScriptKind:
    if _DEVANAGARI_RE.match(ch) or ch in "।॥":
        return "deva"
    return "latin"


def iter_script_runs(text: str) -> list[tuple[ScriptKind, str]]:
    """Split Hinglish into Devanagari vs Latin/ASCII runs for dual-font drawing.

    Spaces stay attached to the preceding run (leading spaces join the first
    non-space run). Latin covers A–Z names, digits, and punctuation Devanagari
    TTFs typically lack (. ? ! … after normalize, etc.).
    """
    if not text:
        return []
    runs: list[tuple[ScriptKind, str]] = []
    buf: list[str] = []
    kind: ScriptKind | None = None

    def flush() -> None:
        nonlocal buf, kind
        if buf and kind is not None:
            runs.append((kind, "".join(buf)))
        buf = []
        kind = None

    for ch in text:
        if ch.isspace():
            buf.append(ch)
            continue
        this = _char_script_kind(ch)
        if kind is None:
            kind = this
            buf.append(ch)
        elif this == kind:
            buf.append(ch)
        else:
            flush()
            kind = this
            buf.append(ch)
    flush()
    if not runs and buf:
        return [("latin", "".join(buf))]
    return runs


def contains_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text or ""))


def hindi_font_paths(config: AppConfig, *, bold: bool = True) -> list[Path]:
    """Ordered Hindi font file candidates (bundled → OS)."""
    regular_name = "NotoSansDevanagari-Regular.ttf"
    bold_name = "NotoSansDevanagari-Bold.ttf"
    return [
        config.resolve_asset(config.brand.caption_font),
        config.resolve_asset(config.brand.hindi_quote_font),
        config.resolve_asset(f"assets/fonts/{bold_name if bold else regular_name}"),
        config.resolve_asset(f"assets/fonts/{regular_name}"),
        ROOT_DIR / "assets/fonts/AnekDevanagari-ExtraBold.ttf",
        ROOT_DIR / "assets/fonts/NotoSansDevanagari-Bold.ttf",
        ROOT_DIR / "assets/fonts/NotoSansDevanagari-Regular.ttf",
        ROOT_DIR / "assets/fonts/NotoSerifDevanagari-Regular.ttf",
        ROOT_DIR / "assets/fonts/TiroDevanagariHindi-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansDevanagari-Bold.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf"),
        Path("C:/Windows/Fonts/NirmalaB.ttf"),
        Path("C:/Windows/Fonts/Nirmala.ttf"),
        Path("C:/Windows/Fonts/mangal.ttf"),
        Path("C:/Windows/Fonts/Mangal.ttf"),
    ]


def latin_font_paths(config: AppConfig) -> list[Path]:
    """Latin-capable fonts for ASCII/names embedded in Hinglish lines."""
    return [
        config.resolve_asset(config.brand.body_font),
        ROOT_DIR / "assets/fonts/Inter-Regular.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        config.resolve_asset(config.brand.quote_font),
        Path(config.brand.quote_font),
        ROOT_DIR / "assets/fonts/BebasNeue-Regular.ttf",
        Path("C:/Windows/Fonts/georgiab.ttf"),
        Path("C:/Windows/Fonts/timesbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]


def resolve_hindi_font_path(config: AppConfig, *, bold: bool = True) -> Path | None:
    for path in hindi_font_paths(config, bold=bold):
        if path.exists():
            return path
    return None


def resolve_latin_font_path(config: AppConfig) -> Path | None:
    for path in latin_font_paths(config):
        if path.exists():
            return path
    return None
