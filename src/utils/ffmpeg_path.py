"""Locate ffmpeg executable on the system or via imageio-ffmpeg."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def get_ffmpeg_exe() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg (winget install Gyan.FFmpeg) "
            "or run: pip install imageio-ffmpeg"
        ) from exc


def get_media_duration(path: Path) -> float | None:
    try:
        import ffmpeg

        probe = ffmpeg.probe(str(path))
        return float(probe["format"]["duration"])
    except Exception:
        pass

    try:
        result = subprocess.run(
            [get_ffmpeg_exe(), "-i", str(path)],
            capture_output=True,
            text=True,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
        if match:
            hours, minutes, seconds = match.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        return None
    return None
