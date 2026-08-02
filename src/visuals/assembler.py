"""FFmpeg-based reel assembler."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.utils.ffmpeg_path import get_ffmpeg_exe, get_media_duration

from src.brand.templates import BrandTemplates
from src.book_queue.models import EpisodeContext, ScriptOutput
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.visuals.caption_renderer import ass_filter_path, write_ass_subtitles
from src.visuals.captions import CaptionGenerator, CaptionSegment


class ReelAssembler:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.brand = BrandTemplates(config)
        self.captions = CaptionGenerator(config, logger)

    def assemble(
        self,
        context: EpisodeContext,
        script: ScriptOutput,
        audio_path: Path,
        stock_paths: list[Path] | Path,
        output_path: Path,
        bgm_path: Path | None = None,
    ) -> Path:
        if isinstance(stock_paths, Path):
            stock_paths = [stock_paths]

        self.logger.start("reel_assembly", str(output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width = self.config.video.width
        height = self.config.video.height
        fps = self.config.video.fps

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            intro_path = tmp_dir / "intro.png"
            outro_path = tmp_dir / "outro.png"
            main_video = tmp_dir / "main.mp4"
            intro_video = tmp_dir / "intro.mp4"
            outro_video = tmp_dir / "outro.mp4"
            captioned = tmp_dir / "captioned.mp4"
            concat_list = tmp_dir / "concat.txt"

            self.brand.save_card(
                self.brand.create_intro_card(width, height),
                intro_path,
            )
            self.brand.save_card(
                self.brand.create_outro_card(width, height, context.episode.episode_num + 1),
                outro_path,
            )

            audio_duration = self._get_duration(audio_path)
            intro_dur = self.config.brand.intro_duration_sec
            outro_dur = self.config.brand.outro_duration_sec
            main_dur = max(1.0, audio_duration)

            self._create_image_video(intro_path, intro_video, intro_dur, fps, width, height)
            self._create_montage_video(stock_paths, main_video, main_dur, fps, width, height, tmp_dir)
            self._create_image_video(outro_path, outro_video, outro_dur, fps, width, height)

            segments = self.captions.generate(audio_path)
            if script.on_screen_text:
                hook_segments = [
                    CaptionSegment(script.on_screen_text[0], 0.0, min(3.0, main_dur))
                ]
                segments = hook_segments + segments

            self._overlay_captions(main_video, captioned, segments, width, height, tmp_dir)

            concat_list.write_text(
                f"file '{intro_video.as_posix()}'\n"
                f"file '{captioned.as_posix()}'\n"
                f"file '{outro_video.as_posix()}'\n",
                encoding="utf-8",
            )

            combined = tmp_dir / "combined.mp4"
            self._run_ffmpeg([
                "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-c", "copy", str(combined),
            ])

            padded_audio = tmp_dir / "padded_audio.aac"
            self._pad_audio(audio_path, padded_audio, intro_dur, outro_dur)

            final_audio = padded_audio
            if bgm_path and bgm_path.exists():
                mixed = tmp_dir / "mixed_audio.aac"
                vol = self.config.video.bgm_volume
                self._mix_bgm(padded_audio, bgm_path, mixed, bgm_volume=vol)
                final_audio = mixed
                self.logger.info(f"reel_assembly | BGM mixed at {vol:.0%}: {bgm_path.name}")

            self._run_ffmpeg([
                "-y", "-i", str(combined), "-i", str(final_audio),
                "-c:v", "copy", "-c:a", "aac",
                "-map", "0:v:0", "-map", "1:a:0",
                str(output_path),
            ])

        self.logger.ok("reel_assembly", str(output_path))
        return output_path

    def _get_duration(self, path: Path) -> float:
        duration = get_media_duration(path)
        return duration if duration is not None else 25.0

    def _scale_pad_filter(self, width: int, height: int) -> str:
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},format=yuv420p"
        )

    def _create_image_video(
        self, image: Path, output: Path, duration: float, fps: int, width: int, height: int,
        ken_burns: bool = False,
    ) -> None:
        vf = self._scale_pad_filter(width, height)
        if ken_burns:
            vf += (
                f",zoompan=z='min(zoom+0.0008,1.12)':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d={int(duration * fps)}:s={width}x{height}:fps={fps}"
            )
        self._run_ffmpeg([
            "-y", "-loop", "1", "-i", str(image),
            "-t", str(duration), "-vf", vf,
            "-r", str(fps), "-pix_fmt", "yuv420p", str(output),
        ])

    def _create_montage_video(
        self,
        clips: list[Path],
        output: Path,
        duration: float,
        fps: int,
        width: int,
        height: int,
        tmp_dir: Path,
    ) -> None:
        if not clips:
            raise RuntimeError("No stock clips provided for montage")
        if len(clips) == 1:
            self._create_single_clip(clips[0], output, duration, fps, width, height)
            return

        seg_dur = duration / len(clips)
        segment_paths: list[Path] = []
        for i, clip in enumerate(clips):
            seg_out = tmp_dir / f"montage_seg_{i}.mp4"
            self._create_single_clip(clip, seg_out, seg_dur, fps, width, height)
            segment_paths.append(seg_out)

        concat_file = tmp_dir / "montage_concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segment_paths),
            encoding="utf-8",
        )
        self._run_ffmpeg([
            "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", str(output),
        ])

    def _create_single_clip(
        self, clip: Path, output: Path, duration: float, fps: int, width: int, height: int,
    ) -> None:
        if clip.suffix.lower() in (".mp4", ".mov", ".webm"):
            self._run_ffmpeg([
                "-y", "-stream_loop", "-1", "-i", str(clip),
                "-t", str(duration), "-vf", self._scale_pad_filter(width, height),
                "-r", str(fps), "-an", "-pix_fmt", "yuv420p", str(output),
            ])
        else:
            self._create_image_video(clip, output, duration, fps, width, height, ken_burns=True)

    def _overlay_captions(
        self,
        input_video: Path,
        output_video: Path,
        segments: list[CaptionSegment],
        width: int,
        height: int,
        tmp_dir: Path | None = None,
    ) -> None:
        if not segments or all(not s.text for s in segments):
            import shutil
            shutil.copy(input_video, output_video)
            return

        ass_path = (tmp_dir or input_video.parent) / "captions.ass"
        write_ass_subtitles(segments, ass_path, width=width, height=height)
        vf = ass_filter_path(ass_path)

        self._run_ffmpeg([
            "-y", "-i", str(input_video), "-vf", vf,
            "-c:a", "copy", str(output_video),
        ])

    def _pad_audio(self, input_audio: Path, output_audio: Path, delay_sec: float, pad_end_sec: float) -> None:
        delay_ms = int(delay_sec * 1000)
        self._run_ffmpeg([
            "-y", "-i", str(input_audio),
            "-af", f"adelay={delay_ms}|{delay_ms},apad=pad_dur={pad_end_sec}",
            "-c:a", "aac", str(output_audio),
        ])

    def _mix_bgm(self, voiceover: Path, bgm: Path, output: Path, bgm_volume: float = 0.12) -> None:
        """Mix novel BGM under voiceover at low volume."""
        self._run_ffmpeg([
            "-y", "-i", str(voiceover), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex",
            f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2",
            "-c:a", "aac", str(output),
        ])

    def _run_ffmpeg(self, args: list[str]) -> None:
        cmd = [get_ffmpeg_exe(), *args]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-1500:]}")
