"""Download royalty-free retention SFX into assets/sfx_library.

Sources (all free, no ElevenLabs):
  1. Mixkit CDN — direct WAV/MP3 URLs (Mixkit SFX Free License)
  2. ffmpeg synthesis — same generators as src/visuals/sfx.py (offline fallback)

Pixabay does not expose a public sound-effects API; if PIXABAY_API_KEY is set we
log that and continue with the sources above.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from src.config import load_config
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.visuals.sfx import SFX_FILES, SfxMixer

MIXKIT_LICENSE = "Mixkit SFX Free License (https://mixkit.co/license/#sfxFree)"


@dataclass(frozen=True)
class SfxSource:
    filename: str
    sfx_type: str
    title: str
    urls: tuple[str, ...]
    max_duration_sec: float
    fade_out_sec: float = 0.15


SFX_SOURCES: tuple[SfxSource, ...] = (
    SfxSource(
        filename="hook_impact.wav",
        sfx_type="hook_impact",
        title="Fast impact blow (Mixkit #2884)",
        urls=(
            "https://assets.mixkit.co/active_storage/sfx/2884/2884.wav",
            "https://assets.mixkit.co/active_storage/sfx/2884/2884-preview.mp3",
            "https://assets.mixkit.co/active_storage/sfx/2303/2303-preview.mp3",
        ),
        max_duration_sec=0.40,
        fade_out_sec=0.18,
    ),
    SfxSource(
        filename="whoosh_short.wav",
        sfx_type="whoosh_short",
        title="Quick air woosh (Mixkit #2568)",
        urls=(
            "https://assets.mixkit.co/active_storage/sfx/2568/2568.wav",
            "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
            "https://assets.mixkit.co/active_storage/sfx/1490/1490-preview.mp3",
        ),
        max_duration_sec=0.35,
        fade_out_sec=0.12,
    ),
    SfxSource(
        filename="cliffhanger_rumble.wav",
        sfx_type="cliffhanger_rumble",
        title="Deep cinematic subtle drum impact (Mixkit #549)",
        urls=(
            "https://assets.mixkit.co/active_storage/sfx/549/549.wav",
            "https://assets.mixkit.co/active_storage/sfx/549/549-preview.mp3",
            "https://assets.mixkit.co/active_storage/sfx/2295/2295-preview.mp3",
        ),
        max_duration_sec=1.40,
        fade_out_sec=0.40,
    ),
)


def log(msg: str) -> None:
    print(f"[download_sfx] {msg}")


def try_pixabay(api_key: str) -> None:
    if not api_key:
        return
    log(
        "PIXABAY_API_KEY is set, but Pixabay has no public sound-effects API "
        "(images/videos only). Using Mixkit CDN + ffmpeg fallback."
    )


def download_bytes(url: str, dest: Path) -> None:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def postprocess_audio(
    ffmpeg: str,
    src: Path,
    dest: Path,
    *,
    max_duration_sec: float,
    fade_out_sec: float,
) -> None:
    fade_start = max(0.0, max_duration_sec - fade_out_sec)
    af = (
        f"atrim=0:{max_duration_sec},"
        f"afade=t=out:st={fade_start}:d={fade_out_sec},"
        "highpass=f=40,"
        "alimiter=limit=0.95"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-af",
        af,
        "-ar",
        "44100",
        "-ac",
        "1",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-800:])


def generate_with_ffmpeg(sfx_type: str, dest: Path) -> None:
    from src.pipeline.logger import PipelineLogger

    mixer = SfxMixer(load_config(), PipelineLogger("download_sfx"))
    mixer._generate_sfx(sfx_type, dest)


def ensure_sfx(
    source: SfxSource,
    library_dir: Path,
    *,
    force: bool,
) -> dict[str, str | int]:
    dest = library_dir / source.filename
    if dest.exists() and not force:
        size = dest.stat().st_size
        log(f"skip {source.filename} ({size:,} bytes, already exists)")
        return {
            "file": source.filename,
            "status": "skipped",
            "source": "existing",
            "bytes": size,
        }

    ffmpeg = get_ffmpeg_exe()
    library_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        raw = tmp_dir / "raw_audio"
        last_err = ""

        for url in source.urls:
            ext = ".mp3" if url.endswith(".mp3") else ".wav"
            raw_path = raw.with_suffix(ext)
            try:
                log(f"fetch {source.filename} <- {url}")
                download_bytes(url, raw_path)
                postprocess_audio(
                    ffmpeg,
                    raw_path,
                    dest,
                    max_duration_sec=source.max_duration_sec,
                    fade_out_sec=source.fade_out_sec,
                )
                size = dest.stat().st_size
                log(f"saved {source.filename} ({size:,} bytes) from {url}")
                return {
                    "file": source.filename,
                    "status": "downloaded",
                    "source": url,
                    "title": source.title,
                    "license": MIXKIT_LICENSE,
                    "bytes": size,
                }
            except Exception as exc:
                last_err = str(exc)
                log(f"  failed: {exc}")

    log(f"fallback ffmpeg synthesis for {source.filename}")
    generate_with_ffmpeg(source.sfx_type, dest)
    size = dest.stat().st_size
    log(f"generated {source.filename} ({size:,} bytes) via ffmpeg")
    return {
        "file": source.filename,
        "status": "generated",
        "source": "ffmpeg (src/visuals/sfx.py)",
        "bytes": size,
    }


def validate_filenames() -> None:
    expected = set(SFX_FILES.values())
    provided = {s.filename for s in SFX_SOURCES}
    if expected != provided:
        missing = expected - provided
        extra = provided - expected
        raise RuntimeError(
            f"SFX filename mismatch. missing={missing!r} extra={extra!r}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download free retention SFX into assets/sfx_library"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even when files already exist",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = load_config()
    validate_filenames()
    try_pixabay(config.pixabay_api_key)

    library_dir = config.path("sfx_library")
    log(f"library dir: {library_dir}")

    results: list[dict[str, str | int]] = []
    for source in SFX_SOURCES:
        results.append(ensure_sfx(source, library_dir, force=args.force))

    log("summary:")
    for row in results:
        name = row["file"]
        status = row["status"]
        src = row["source"]
        size = row["bytes"]
        log(f"  {name}: {status} | {size:,} bytes | {src}")

    log("done")


if __name__ == "__main__":
    main()
