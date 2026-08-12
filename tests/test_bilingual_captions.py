"""Bilingual caption / slide helpers."""

from __future__ import annotations

from src.visuals.bilingual import bilingual_slide_texts, make_bilingual_segments, split_parallel
from src.visuals.captions import CaptionSegment


def test_split_parallel_packs_sentences() -> None:
    text = "One. Two. Three. Four."
    parts = split_parallel(text, 2)
    assert len(parts) == 2
    assert all(parts)


def test_make_bilingual_segments_stacks_english() -> None:
    segs = [
        CaptionSegment("Police ने देखा", 0.0, 2.0, style="Hook"),
        CaptionSegment("वो गायब हो गई", 2.0, 5.0),
    ]
    out = make_bilingual_segments(
        segs,
        "She vanished into the night. The secret grew.",
        english_on_screen=["Police saw it"],
    )
    assert "\n" in out[0].text
    assert out[0].text.startswith("Police ने देखा")
    assert "Police saw it" in out[0].text
    assert "\n" in out[1].text


def test_bilingual_slide_texts() -> None:
    slides = bilingual_slide_texts(["हिंदी लाइन"], ["English line"])
    assert slides == ["हिंदी लाइन\n\nEnglish line"]
