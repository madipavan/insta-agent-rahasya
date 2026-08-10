"""BGM mix verification helpers — detect whether underscore is actually present."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from src.utils.ffmpeg_path import get_ffmpeg_exe


def measure_mean_volume(
    audio_path: Path,
    *,
    start_sec: float = 0.0,
    duration_sec: float = 1.0,
    audio_filter: str = "",
) -> float | None:
    """Return mean volume (dB) for a slice of audio, optionally filtered."""
    filters = []
    if audio_filter:
        filters.append(audio_filter)
    filters.append("volumedetect")
    cmd = [
        get_ffmpeg_exe(),
        "-hide_banner",
        "-ss",
        str(start_sec),
        "-t",
        str(duration_sec),
        "-i",
        str(audio_path),
        "-af",
        ",".join(filters),
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    for line in (result.stderr or "").splitlines():
        match = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", line)
        if match:
            return float(match.group(1))
    return None


def bgm_band_delta_db(
    mixed_audio: Path,
    voice_only_audio: Path,
    *,
    highpass_hz: int = 2500,
    start_sec: float = 0.0,
    duration_sec: float = 1.0,
) -> float | None:
    """How much louder the high band is in mixed vs voice-only (BGM bed detector)."""
    af = f"highpass=f={highpass_hz}"
    mixed_db = measure_mean_volume(
        mixed_audio,
        start_sec=start_sec,
        duration_sec=duration_sec,
        audio_filter=af,
    )
    voice_db = measure_mean_volume(
        voice_only_audio,
        start_sec=start_sec,
        duration_sec=duration_sec,
        audio_filter=af,
    )
    if mixed_db is None or voice_db is None:
        return None
    return mixed_db - voice_db


def has_audible_bgm_bed(
    mixed_audio: Path,
    voice_only_audio: Path,
    *,
    min_delta_db: float = 3.0,
    highpass_hz: int = 2500,
    start_sec: float = 0.0,
    duration_sec: float = 1.0,
) -> bool:
    delta = bgm_band_delta_db(
        mixed_audio,
        voice_only_audio,
        highpass_hz=highpass_hz,
        start_sec=start_sec,
        duration_sec=duration_sec,
    )
    return delta is not None and delta >= min_delta_db


def probe_audio_codec(video_path: Path) -> str | None:
    """Detect audio codec — works with ffprobe or ffmpeg stderr fallback."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        probe = subprocess.run(
            [
                ffprobe,
                "-hide_banner",
                "-print_format",
                "json",
                "-show_streams",
                str(video_path),
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0 and probe.stdout:
            try:
                info = json.loads(probe.stdout)
                for stream in info.get("streams", []):
                    if stream.get("codec_type") == "audio":
                        return stream.get("codec_name")
            except json.JSONDecodeError:
                pass

    result = subprocess.run(
        [get_ffmpeg_exe(), "-hide_banner", "-i", str(video_path)],
        capture_output=True,
        text=True,
    )
    for line in (result.stderr or "").splitlines():
        if "Audio:" in line:
            match = re.search(r"Audio:\s*(\w+)", line)
            if match:
                return match.group(1)
    return None
