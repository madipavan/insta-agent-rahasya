"""Sarvam AI Bulbul v3 voiceover — Hindi storytelling TTS."""

from __future__ import annotations

import base64
import re
import subprocess
import tempfile
from pathlib import Path

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.voiceover.base import VoiceoverBase


class SarvamVoiceover(VoiceoverBase):
    API_URL = "https://api.sarvam.ai/text-to-speech"
    CHUNK_SIZE = 2400  # bulbul:v3 max 2500

    def generate(self, text: str, output_path: Path) -> Path:
        speaker = self.config.sarvam_speaker or "priya"
        self.logger.start(
            "voiceover",
            f"sarvam ({speaker}, pace={self.config.sarvam_pace}) -> {output_path}",
        )
        if not self.config.sarvam_api_key:
            raise ValueError("SARVAM_API_KEY not set in .env")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        performance_text = self._prepare_performance_text(text)
        chunks = self._split_text(performance_text)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            parts: list[Path] = []
            for i, chunk in enumerate(chunks):
                part = tmp_dir / f"part_{i}.mp3"
                self._synthesize_chunk(chunk, part, speaker)
                parts.append(part)

            if len(parts) == 1:
                import shutil
                shutil.copy(parts[0], output_path)
            else:
                self._concat_audio(parts, output_path)

        duration = self._get_duration(output_path)
        duration = self._enforce_max_duration(output_path, duration)
        self._check_duration(duration)
        self.logger.ok("voiceover", f"sarvam ({speaker}) {duration:.1f}s")
        return output_path

    def _prepare_performance_text(self, text: str) -> str:
        t = text.strip()
        t = re.sub(r"…+", " … ", t)
        t = re.sub(r"\.{3,}", " … ", t)
        t = re.sub(r"\s*—\s*", " — ", t)
        t = re.sub(r"( … ){2,}", " … ", t)
        return t.strip()

    def _synthesize_chunk(self, text: str, output_path: Path, speaker: str) -> None:
        headers = {
            "api-subscription-key": self.config.sarvam_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "language_code": self.config.sarvam_language_code or "hi-IN",
            "speaker": speaker.lower(),
            "model": self.config.sarvam_model or "bulbul:v3",
            "pace": self.config.sarvam_pace,
            "temperature": self.config.sarvam_temperature,
            "output_audio_codec": "mp3",
            "speech_sample_rate": "24000",
        }

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
                err = body.get("error", {})
                detail = err.get("message", "") or str(body)
            except Exception:
                detail = response.text[:200]

            if response.status_code in (401, 403):
                raise requests.HTTPError(
                    f"Sarvam API key invalid ({response.status_code}). {detail}",
                    response=response,
                )
            if response.status_code in (402, 429):
                raise requests.HTTPError(
                    f"Sarvam {response.status_code}: {detail}",
                    response=response,
                )
            response.raise_for_status()

        data = response.json()
        audios = data.get("audios") or []
        if not audios:
            raise RuntimeError("Sarvam returned no audio")

        audio_bytes = base64.b64decode("".join(audios))
        output_path.write_bytes(audio_bytes)

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
