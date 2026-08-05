"""Fish Audio TTS voiceover generation (free tier: s2.1-pro-free)."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.voiceover.base import VoiceoverBase


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
        chunks = self._split_text(performance_text)

        if len(chunks) == 1:
            self._synthesize_chunk(chunks[0], output_path, model)
        else:
            self.logger.info(f"voiceover | fish-audio splitting into {len(chunks)} chunks")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                parts: list[Path] = []
                for i, chunk in enumerate(chunks):
                    part = tmp_dir / f"part_{i}.mp3"
                    self._synthesize_chunk(chunk, part, model)
                    parts.append(part)
                self._concat_audio(parts, output_path)

        duration = self._get_duration(output_path)
        duration = self._enforce_max_duration(output_path, duration)
        self._check_duration(duration)
        self.logger.ok("voiceover", f"fish-audio {duration:.1f}s")
        return output_path

    def _prepare_performance_text(self, text: str) -> str:
        t = text.strip()
        t = re.sub(r"…+", "…", t)
        t = re.sub(r"\.{3,}", "…", t)
        t = re.sub(r"\s*—\s*", " — ", t)
        return t.strip()

    def _synthesize_chunk(self, text: str, output_path: Path, model: str) -> None:
        headers = {
            "Authorization": f"Bearer {self.config.fish_audio_api_key}",
            "Content-Type": "application/json",
            "model": model,
        }
        payload: dict = {
            "text": text,
            "format": "mp3",
            "normalize": True,
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

    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self.CHUNK_SIZE:
            return [text]
        sentences = re.split(r"(?<=[।.!?…])\s+", text.strip())
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if not sentence:
                continue
            if len(current) + len(sentence) + 1 <= self.CHUNK_SIZE:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
        return chunks or [text]

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
