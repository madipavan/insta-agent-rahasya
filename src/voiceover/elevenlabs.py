"""ElevenLabs voiceover generation."""

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


class ElevenLabsVoiceover(VoiceoverBase):
    CHUNK_SIZE = 1800

    def generate(self, text: str, output_path: Path) -> Path:
        voice_label = self.config.voice_name or self.config.voice_id
        self.logger.start("voiceover", f"elevenlabs ({voice_label}) -> {output_path}")
        if not self.config.elevenlabs_api_key:
            raise ValueError("ELEVENLABS_API_KEY not set in .env")
        if not self.config.voice_id:
            raise ValueError("voice_id not set in config.yaml")

        chunks = self._split_text(text)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if len(chunks) == 1:
            self._synthesize_chunk(chunks[0], output_path)
        else:
            self.logger.info(f"voiceover | splitting into {len(chunks)} chunks for long script")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                part_paths: list[Path] = []
                for i, chunk in enumerate(chunks):
                    part = tmp_dir / f"part_{i}.mp3"
                    self._synthesize_chunk(chunk, part)
                    part_paths.append(part)
                self._concat_audio(part_paths, output_path)

        duration = self._get_duration(output_path)
        self._check_duration(duration)
        self.logger.ok("voiceover", f"elevenlabs ({voice_label}) {duration:.1f}s")
        return output_path

    def _synthesize_chunk(self, text: str, output_path: Path) -> None:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.voice_id}"
        headers = {
            "xi-api-key": self.config.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "language_code": "hi",
            "voice_settings": {
                "stability": 0.35,
                "similarity_boost": 0.75,
                "style": 0.55,
            },
        }

        response = requests.post(url, json=payload, headers=headers, timeout=300)
        if not response.ok:
            detail = ""
            try:
                body = response.json().get("detail", {})
                if isinstance(body, dict):
                    detail = body.get("message", "") or body.get("code", "")
                else:
                    detail = str(body)
            except Exception:
                detail = response.text[:200]

            if response.status_code == 401:
                raise requests.HTTPError(
                    f"ElevenLabs API key invalid (401). {detail}",
                    response=response,
                )
            if response.status_code == 402:
                if "paid_plan" in detail.lower() or "library voice" in detail.lower():
                    raise requests.HTTPError(
                        f"ElevenLabs 402: Tarini is a library voice — requires a PAID plan "
                        f"for API use (free tier cannot use library voices via API). {detail}",
                        response=response,
                    )
                raise requests.HTTPError(
                    f"ElevenLabs payment required (402). {detail}",
                    response=response,
                )
            response.raise_for_status()
        output_path.write_bytes(response.content)

    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self.CHUNK_SIZE:
            return [text]
        sentences = re.split(r"(?<=[।.!?])\s+", text.strip())
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


VoiceoverGenerator = ElevenLabsVoiceover
