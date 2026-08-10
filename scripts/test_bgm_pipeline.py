"""Run BGM pipeline diagnostics locally — no ElevenLabs / TTS API calls."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.pipeline.logger import PipelineLogger
from src.visuals.assembler import ReelAssembler
from src.visuals.bgm_audio import bgm_band_delta_db, has_audible_bgm_bed, probe_audio_codec

# Reuse test tone helpers — no external APIs.
from tests.test_bgm_pipeline import _make_tone_mp3, _make_voice_mp3


def main() -> None:
    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    asm = ReelAssembler(config, logger)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        voice = tmp_dir / "voice.mp3"
        bgm = tmp_dir / "bgm.mp3"
        padded = tmp_dir / "padded.aac"
        mixed = tmp_dir / "mixed.aac"

        _make_voice_mp3(voice, duration=8.0)
        _make_tone_mp3(bgm, freq=3200, duration=15.0)
        asm._pad_audio(voice, padded, delay_sec=1.0, pad_end_sec=1.0)
        asm._mix_bgm(padded, bgm, mixed)

        delta = bgm_band_delta_db(mixed, padded, highpass_hz=2500, start_sec=2.0, duration_sec=2.0)
        audible = has_audible_bgm_bed(mixed, padded, start_sec=2.0, duration_sec=2.0)

        print("=== BGM pipeline diagnostic (no TTS API) ===")
        print(f"mix adds high-band energy: {delta:+.1f} dB" if delta is not None else "mix check failed")
        print(f"audible BGM bed: {audible}")
        print(f"mixed file: {mixed} ({mixed.stat().st_size} bytes)")

        novel_bgm = config.path("novels_pdf_dir").parent / "novels" / "1_the_thirty_nine_steps" / "bgm.mp3"
        print(f"novel bgm on disk: {novel_bgm.exists()} ({novel_bgm})")

        if not audible:
            print("FAIL: BGM not detectable in mix")
            sys.exit(1)
        print("OK")


if __name__ == "__main__":
    main()
