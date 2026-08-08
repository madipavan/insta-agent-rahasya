"""Retention SFX layer — hook impact, cut whooshes, cliffhanger sting."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe

SFX_FILES = {
    "hook_impact": "hook_impact.wav",
    "whoosh_short": "whoosh_short.wav",
    "cliffhanger_rumble": "cliffhanger_rumble.wav",
}


@dataclass(frozen=True)
class SfxPlacement:
    time_sec: float
    sfx_type: str
    volume: float


def build_sfx_placements(
    duration: float,
    clip_count: int,
    *,
    cliffhanger_before_end_sec: float = 8.0,
    hook_volume: float = 0.35,
    whoosh_volume: float = 0.22,
    cliffhanger_volume: float = 0.30,
) -> list[SfxPlacement]:
    """Place retention SFX at hook, montage cuts, and cliffhanger window."""
    if duration <= 0:
        return []

    placements: list[SfxPlacement] = [
        SfxPlacement(0.0, "hook_impact", hook_volume),
    ]

    clip_count = max(1, clip_count)
    if clip_count > 1:
        seg = duration / clip_count
        for i in range(1, clip_count):
            placements.append(SfxPlacement(i * seg, "whoosh_short", whoosh_volume))

    cliff_t = max(0.0, duration - cliffhanger_before_end_sec)
    if cliff_t > 1.0 and cliff_t < duration - 0.5:
        placements.append(SfxPlacement(cliff_t, "cliffhanger_rumble", cliffhanger_volume))

    return placements


class SfxMixer:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.library_dir = config.path("sfx_library")

    def ensure_library(self) -> None:
        """Create built-in SFX files if the library folder is empty."""
        self.library_dir.mkdir(parents=True, exist_ok=True)
        for sfx_type, filename in SFX_FILES.items():
            path = self.library_dir / filename
            if not path.exists():
                self._generate_sfx(sfx_type, path)
                self.logger.info(f"sfx | generated {filename}")

    def apply(
        self,
        voiceover: Path,
        output: Path,
        placements: list[SfxPlacement],
    ) -> Path:
        if not placements:
            shutil.copy(voiceover, output)
            return output

        self.ensure_library()
        resolved: list[tuple[Path, float, float]] = []
        for p in placements:
            sfx_path = self.library_dir / SFX_FILES.get(p.sfx_type, "")
            if sfx_path.exists():
                resolved.append((sfx_path, p.time_sec, p.volume))

        if not resolved:
            shutil.copy(voiceover, output)
            return output

        output.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = get_ffmpeg_exe()
        inputs: list[str] = ["-y", "-i", str(voiceover)]
        filter_parts: list[str] = []
        mix_labels = ["[0:a]"]

        for i, (sfx_path, start_sec, volume) in enumerate(resolved):
            inputs.extend(["-i", str(sfx_path)])
            delay_ms = int(start_sec * 1000)
            label = f"sfx{i}"
            filter_parts.append(
                f"[{i + 1}:a]adelay={delay_ms}|{delay_ms},volume={volume}[{label}]"
            )
            mix_labels.append(f"[{label}]")

        n_inputs = len(mix_labels)
        filter_complex = (
            ";".join(filter_parts)
            + f";{''.join(mix_labels)}amix=inputs={n_inputs}:duration=first:"
            "dropout_transition=0:normalize=0,alimiter=limit=0.98"
        )

        cmd = [
            ffmpeg,
            *inputs,
            "-filter_complex",
            filter_complex,
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"SFX mix failed: {result.stderr[-1500:]}")

        self.logger.info(
            f"sfx | mixed {len(resolved)} effects onto voiceover -> {output.name}"
        )
        return output

    def _generate_sfx(self, sfx_type: str, output: Path) -> None:
        ffmpeg = get_ffmpeg_exe()
        generators = {
            "hook_impact": self._gen_hook_impact,
            "whoosh_short": self._gen_whoosh,
            "cliffhanger_rumble": self._gen_cliffhanger,
        }
        generator = generators.get(sfx_type, self._gen_whoosh)
        generator(ffmpeg, output)

    def _gen_hook_impact(self, ffmpeg: str, output: Path) -> None:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "aevalsrc=0.6*sin(2*PI*90*t)*exp(-10*t):d=0.35:s=44100",
            "-af",
            "afade=t=out:st=0.15:d=0.2,highpass=f=60",
            str(output),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def _gen_whoosh(self, ffmpeg: str, output: Path) -> None:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=white:duration=0.28:sample_rate=44100:amplitude=0.35",
            "-af",
            "highpass=f=400,lowpass=f=4000,afade=t=in:st=0:d=0.02,afade=t=out:st=0.12:d=0.16",
            str(output),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    def _gen_cliffhanger(self, ffmpeg: str, output: Path) -> None:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=55:duration=1.4:sample_rate=44100",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=brown:duration=1.4:sample_rate=44100:amplitude=0.08",
            "-filter_complex",
            "[0:a]volume=0.25[s];[1:a]lowpass=f=120[n];[s][n]amix=inputs=2:duration=first,"
            "afade=t=in:st=0:d=0.15,afade=t=out:st=1.0:d=0.4",
            str(output),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
