"""Fish Audio TTS voiceover generation (free tier: s2.1-pro-free)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.voiceover.base import VoiceoverBase

_STORYTELLING_OPENING = (
    "[speaking slowly, with deep emotional Hindi thriller storytelling, "
    "like a suspense film dubbing narrator] "
)
_CLIFFHANGER_CUE = "[voice drops, tense whisper] "


class FishAudioVoiceover(VoiceoverBase):
    API_URL = "https://api.fish.audio/v1/tts"
    CHUNK_SIZE = 1800

    def generate(self, text: str, output_path: Path) -> Path:
        model = self.config.fish_audio_model or "s2.1-pro-free"
        self.logger.start("voiceover", f"fish-audio ({model}) -> {output_path}")
        if not self.config.fish_audio_api_key:
            raise ValueError("FISH_AUDIO_API_KEY not set in .env")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        performance_text = self._prepare_performance_text(text)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            if self.config.fish_audio_sentence_mode:
                units = self._split_sentences(performance_text) or [performance_text]
                label = f"sentence mode ({len(units)} lines)"
            else:
                units = self._split_text(performance_text)
                label = f"{len(units)} chunk(s)"

            self.logger.info(f"voiceover | fish-audio {label}")
            parts: list[Path] = []
            for i, unit in enumerate(units):
                part = tmp_dir / f"part_{i}.mp3"
                is_last = i == len(units) - 1
                self._synthesize_chunk(
                    unit,
                    part,
                    model,
                    dramatic_opening=(i == 0),
                    cliffhanger_close=is_last and self.config.fish_audio_sentence_mode,
                )
                parts.append(part)

            if len(parts) == 1:
                shutil.copy(parts[0], output_path)
            else:
                self._concat_audio_with_pauses(
                    parts,
                    output_path,
                    tmp_dir,
                    self.config.fish_audio_sentence_pause_sec,
                )

        duration = self._get_duration(output_path)
        duration = self._enforce_max_duration(output_path, duration)
        self._check_duration(duration)
        self.logger.ok("voiceover", f"fish-audio {duration:.1f}s")
        return output_path

    def _prepare_performance_text(self, text: str) -> str:
        """Add dramatic pauses and spacing for Fish storytelling delivery."""
        t = text.strip()
        t = re.sub(r"…+", " … ", t)
        t = re.sub(r"\.{3,}", " … ", t)
        t = re.sub(r"\s*—\s*", " — ", t)
        t = re.sub(r"(\?)\s+", r"\1 … ", t)
        t = re.sub(r"(!)\s+", r"\1 … ", t)
        t = re.sub(r"( … ){2,}", " … ", t)
        return t.strip()

    def _decorate_sentence(
        self,
        text: str,
        *,
        dramatic_opening: bool,
        cliffhanger_close: bool,
    ) -> str:
        t = text.strip()
        if dramatic_opening:
            t = _STORYTELLING_OPENING + t
        if cliffhanger_close:
            t = _CLIFFHANGER_CUE + t
        return t

    def _synthesize_chunk(
        self,
        text: str,
        output_path: Path,
        model: str,
        *,
        dramatic_opening: bool = False,
        cliffhanger_close: bool = False,
    ) -> None:
        spoken = self._decorate_sentence(
            text,
            dramatic_opening=dramatic_opening,
            cliffhanger_close=cliffhanger_close,
        )
        headers = {
            "Authorization": f"Bearer {self.config.fish_audio_api_key}",
            "Content-Type": "application/json",
            "model": model,
        }
        payload: dict = {
            "text": spoken,
            "format": "mp3",
            "normalize": True,
            "temperature": self.config.fish_audio_temperature,
            "top_p": 0.8,
            "latency": self.config.fish_audio_latency,
            "chunk_length": 200,
            "min_chunk_length": 30,
            "condition_on_previous_chunks": True,
            "repetition_penalty": 1.15,
            "prosody": {
                "speed": self.config.fish_audio_speed,
                "volume": 0,
                "normalize_loudness": True,
            },
        }
        if self.config.fish_audio_voice_id:
            payload["reference_id"] = self.config.fish_audio_voice_id

        response = requests.post(
            self.API_URL,
            json=payload,
            headers=headers,
            timeout=300,
        )
        if not response.ok:
            detail = ""
            try:
                body = response.json()
                detail = body.get("message", "") or str(body)
            except Exception:
                detail = response.text[:200]

            if response.status_code == 401:
                raise requests.HTTPError(
                    f"Fish Audio API key invalid (401). {detail}",
                    response=response,
                )
            if response.status_code in (402, 429):
                raise requests.HTTPError(
                    f"Fish Audio {response.status_code}: {detail}",
                    response=response,
                )
            response.raise_for_status()

        output_path.write_bytes(response.content)

    def _split_sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[।.!?…])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self.CHUNK_SIZE:
            return [text]
        sentences = self._split_sentences(text)
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= self.CHUNK_SIZE:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
        return chunks or [text]

    def _generate_silence(self, output: Path, duration_sec: float) -> None:
        subprocess.run(
            [
                get_ffmpeg_exe(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=44100:cl=mono:d={duration_sec}",
                "-c:a",
                "libmp3lame",
                "-q:a",
                "4",
                str(output),
            ],
            check=True,
            capture_output=True,
        )

    def _concat_audio_with_pauses(
        self,
        parts: list[Path],
        output_path: Path,
        tmp_dir: Path,
        pause_sec: float,
    ) -> None:
        sequence: list[Path] = []
        silence: Path | None = None
        if pause_sec > 0:
            silence = tmp_dir / "pause.mp3"
            self._generate_silence(silence, pause_sec)

        for i, part in enumerate(parts):
            sequence.append(part)
            if silence and i < len(parts) - 1:
                sequence.append(silence)

        self._concat_audio(sequence, output_path)

    def _concat_audio(self, parts: list[Path], output_path: Path) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            list_path = Path(f.name)
            for part in parts:
                f.write(f"file '{part.as_posix()}'\n")
        try:
            subprocess.run(
                [
                    get_ffmpeg_exe(),
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(list_path),
                    "-c",
                    "copy",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            list_path.unlink(missing_ok=True)
