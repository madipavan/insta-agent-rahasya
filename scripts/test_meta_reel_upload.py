"""Smoke-test Instagram reel rupload (creates container, uploads, does NOT publish)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.pipeline.logger import PipelineLogger
from src.scheduler.meta import MetaScheduler
from src.utils.ffmpeg_path import get_ffmpeg_exe, get_media_duration


def make_test_reel(out: Path, seconds: float = 77.0) -> None:
    ffmpeg = get_ffmpeg_exe()
    # Similar duration/size to production reels (~15MB)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"smptebars=duration={seconds}:size=1080x1920:rate=30",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-profile:v",
            "main",
            "-level",
            "4.0",
            "-pix_fmt",
            "yuv420p",
            "-maxrate",
            "2500k",
            "-bufsize",
            "5000k",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> None:
    cfg = load_config()
    logger = PipelineLogger(cfg.path("logs_dir"))
    meta = MetaScheduler(cfg, logger)

    if not meta.is_configured():
        print("Meta not configured in .env")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw_reel.mp4"
        # 60s synthetic reel — Meta rejects many 77s lavfi test patterns; 60s validates rupload.
        make_test_reel(raw, 60.0)
        print(f"raw: {raw.stat().st_size} bytes, dur={get_media_duration(raw):.1f}s")

        prepared = meta._prepare_reel_for_instagram(raw)
        print(f"prepared: {prepared.stat().st_size} bytes, dur={get_media_duration(prepared):.1f}s")

        container_id = meta._create_reel_container_once(
            prepared,
            "Rahasya upload test — ignore",
            cover_url=None,
        )
        print(f"UPLOAD OK container={container_id} (video_url or rupload)")


if __name__ == "__main__":
    main()
