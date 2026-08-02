"""Free Microsoft Edge TTS voiceover generation."""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.voiceover.base import VoiceoverBase


class EdgeTTSVoiceover(VoiceoverBase):
    HINDI_FEMALE = "hi-IN-SwaraNeural"
    HINDI_MALE = "hi-IN-MadhurNeural"
    ENGLISH_VOICE = "en-IN-PrabhatNeural"
    CHUNK_SIZE = 1800

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        super().__init__(config, logger)
        if config.edge_tts_voice:
            self.voice = config.edge_tts_voice
        elif config.voice_language.lower() in ("hindi", "hi"):
            self.voice = self.HINDI_FEMALE
        else:
            self.voice = self.ENGLISH_VOICE

    def generate(self, text: str, output_path: Path) -> Path:
        self.logger.start("voiceover", f"edge-tts ({self.voice}) -> {output_path}")
        try:
            import edge_tts
        except ImportError as exc:
            raise ImportError("edge-tts not installed. Run: pip install edge-tts") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunks = self._split_text(text)

        if len(chunks) == 1:
            asyncio.run(self._save(edge_tts, chunks[0], output_path))
        else:
            self.logger.info(f"voiceover | edge-tts splitting into {len(chunks)} chunks")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                parts: list[Path] = []
                for i, chunk in enumerate(chunks):
                    part = tmp_dir / f"part_{i}.mp3"
                    asyncio.run(self._save(edge_tts, chunk, part))
                    parts.append(part)
                self._concat_audio(parts, output_path)

        duration = self._get_duration(output_path)
        self._check_duration(duration)
        self.logger.ok("voiceover", f"edge-tts {duration:.1f}s")
        return output_path

    async def _save(self, edge_tts_module, text: str, output_path: Path) -> None:
        communicate = edge_tts_module.Communicate(text, self.voice)
        await communicate.save(str(output_path))

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
                [get_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
                 "-c", "copy", str(output_path)],
                check=True, capture_output=True, text=True,
            )
        finally:
            list_path.unlink(missing_ok=True)
