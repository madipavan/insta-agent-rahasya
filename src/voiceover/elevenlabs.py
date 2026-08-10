"""ElevenLabs voiceover generation."""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.voiceover.base import VoiceoverBase
from src.voiceover.cache import (
    persist_sentence_cache,
    restore_sentence_cache,
    sentence_fingerprint,
)

_V3_CHUNK_SIZE = 4500
_V2_CHUNK_SIZE = 1800
_MAX_RETRIES = 4
_RETRY_BASE_SEC = 3
_CLIFFHANGER_TAG = "[whispers] "


class ElevenLabsVoiceover(VoiceoverBase):
    def generate(self, text: str, output_path: Path) -> Path:
        voice_label = self.config.voice_name or self.config.voice_id
        model = self.config.elevenlabs_model or "eleven_multilingual_v2"
        self.logger.start(
            "voiceover",
            f"elevenlabs ({voice_label}, {model}) -> {output_path}",
        )
        if not self.config.elevenlabs_api_key:
            raise ValueError("ELEVENLABS_API_KEY not set in .env")
        if not self.config.voice_id:
            raise ValueError("voice_id not set in config.yaml")

        performance_text = self._prepare_performance_text(text)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            if self.config.elevenlabs_sentence_mode:
                units = self._split_sentences(performance_text) or [performance_text]
                self.logger.info(f"voiceover | elevenlabs sentence mode ({len(units)} lines)")
                part_paths: list[Path] = []
                for i, sentence in enumerate(units):
                    spoken = self._decorate_sentence(
                        sentence,
                        cliffhanger_close=(
                            self.config.elevenlabs_cliffhanger_whisper
                            and i == len(units) - 1
                        ),
                    )
                    part = tmp_dir / f"part_{i}.mp3"
                    self._synthesize_chunk(spoken, part, model)
                    part_paths.append(part)
            else:
                chunks = self._split_text(performance_text, model)
                if len(chunks) == 1:
                    spoken = self._decorate_sentence(
                        chunks[0],
                        cliffhanger_close=self.config.elevenlabs_cliffhanger_whisper,
                    )
                    self._synthesize_chunk(spoken, output_path, model)
                    duration = self._get_duration(output_path)
                    duration = self._enforce_max_duration(output_path, duration)
                    self._check_duration(duration)
                    self.logger.ok("voiceover", f"elevenlabs ({voice_label}) {duration:.1f}s")
                    return output_path

                self.logger.info(
                    f"voiceover | elevenlabs splitting into {len(chunks)} chunks"
                )
                part_paths = []
                for i, chunk in enumerate(chunks):
                    spoken = self._decorate_sentence(
                        chunk,
                        cliffhanger_close=(
                            self.config.elevenlabs_cliffhanger_whisper
                            and i == len(chunks) - 1
                        ),
                    )
                    part = tmp_dir / f"part_{i}.mp3"
                    self._synthesize_chunk(spoken, part, model)
                    part_paths.append(part)

            self._concat_audio(part_paths, output_path)

        duration = self._get_duration(output_path)
        duration = self._enforce_max_duration(output_path, duration)
        self._check_duration(duration)
        self.logger.ok("voiceover", f"elevenlabs ({voice_label}) {duration:.1f}s")
        return output_path

    def _chunk_size(self, model: str) -> int:
        if "v3" in model:
            return _V3_CHUNK_SIZE
        return _V2_CHUNK_SIZE

    def _prepare_performance_text(self, text: str) -> str:
        t = text.strip()
        t = re.sub(r"…+", " … ", t)
        t = re.sub(r"\.{3,}", " … ", t)
        t = re.sub(r"\s*—\s*", " — ", t)
        t = re.sub(r"(\?)\s+", r"\1 … ", t)
        t = re.sub(r"(!)\s+", r"\1 … ", t)
        t = re.sub(r"( … ){2,}", " … ", t)
        return t.strip()

    def _decorate_sentence(self, text: str, *, cliffhanger_close: bool) -> str:
        t = text.strip()
        if cliffhanger_close and self._supports_audio_tags():
            t = _CLIFFHANGER_TAG + t
        return t

    def _supports_audio_tags(self) -> bool:
        model = (self.config.elevenlabs_model or "").lower()
        return "v3" in model

    def _synthesize_chunk(self, text: str, output_path: Path, model: str) -> None:
        provider = "elevenlabs"
        if self.config.voiceover_cache:
            fp = sentence_fingerprint(text, self.config, provider)
            if restore_sentence_cache(
                output_path=output_path,
                fingerprint=fp,
                config=self.config,
                logger=self.logger,
                provider=provider,
            ):
                return

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.voice_id}"
        headers = {
            "xi-api-key": self.config.elevenlabs_api_key,
            "Content-Type": "application/json",
        }
        payload: dict = {
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": self.config.elevenlabs_stability,
                "similarity_boost": self.config.elevenlabs_similarity_boost,
                "style": self.config.elevenlabs_style,
            },
        }
        if self.config.voice_language:
            payload["language_code"] = self._language_code()

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=300)
                if not response.ok:
                    detail = self._error_detail(response)
                    if response.status_code == 401:
                        raise requests.HTTPError(
                            f"ElevenLabs API key invalid (401). {detail}",
                            response=response,
                        )
                    if response.status_code == 402:
                        raise requests.HTTPError(
                            f"ElevenLabs payment or plan limit (402). {detail}",
                            response=response,
                        )
                    if response.status_code == 429 and attempt < _MAX_RETRIES - 1:
                        wait = _RETRY_BASE_SEC * (2 ** attempt)
                        self.logger.warn(
                            "voiceover",
                            f"elevenlabs rate limited — retry in {wait}s",
                        )
                        time.sleep(wait)
                        continue
                    if response.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                        wait = _RETRY_BASE_SEC * (2 ** attempt)
                        self.logger.warn(
                            "voiceover",
                            f"elevenlabs {response.status_code} — retry in {wait}s",
                        )
                        time.sleep(wait)
                        continue
                    response.raise_for_status()

                output_path.write_bytes(response.content)
                if self.config.voiceover_cache:
                    persist_sentence_cache(
                        output_path=output_path,
                        fingerprint=sentence_fingerprint(text, self.config, provider),
                        config=self.config,
                    )
                return
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    wait = _RETRY_BASE_SEC * (2 ** attempt)
                    self.logger.warn(
                        "voiceover",
                        f"elevenlabs connection error — retry in {wait}s",
                    )
                    time.sleep(wait)
                    continue
                raise

        if last_exc:
            raise last_exc

    def _language_code(self) -> str:
        lang = (self.config.voice_language or "hindi").lower()
        if lang in ("hindi", "hi", "hi-in"):
            return "hi"
        return lang[:2]

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            body = response.json().get("detail", {})
            if isinstance(body, dict):
                return body.get("message", "") or body.get("code", "") or str(body)
            return str(body)
        except Exception:
            return response.text[:200]

    def _split_sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[।.!?…])\s+", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _split_text(self, text: str, model: str) -> list[str]:
        chunk_size = self._chunk_size(model)
        if len(text) <= chunk_size:
            return [text]
        sentences = self._split_sentences(text)
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= chunk_size:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
        return chunks or [text]

    def _concat_audio(self, parts: list[Path], output_path: Path) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
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
