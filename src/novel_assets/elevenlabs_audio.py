"""Per-novel ElevenLabs music + retention SFX — generate once, reuse every episode."""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from src.book_queue.models import Novel
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.visuals.sfx import SFX_FILES

_SOUND_URL = "https://api.elevenlabs.io/v1/sound-generation"
_MUSIC_URL = "https://api.elevenlabs.io/v1/music"
_MAX_RETRIES = 3
_RETRY_BASE_SEC = 3

# Short retention SFX prompts (cinematic thriller / suspense)
_SFX_PROMPTS: dict[str, tuple[str, float]] = {
    "hook_impact": (
        "Deep cinematic impact hit, trailer boom, short punchy low-end thump, no melody",
        1.2,
    ),
    "whoosh_short": (
        "Quick air whoosh transition, short swish for video cut, dry, no reverb tail",
        0.6,
    ),
    "cliffhanger_rumble": (
        "Dark suspense rumble sting, low tension drone swell fading out, cinematic cliffhanger",
        1.8,
    ),
}


def _english_mood(keywords: list[str]) -> list[str]:
    import re

    devanagari = re.compile(r"[\u0900-\u097F]")
    en = [k.strip() for k in keywords if k and not devanagari.search(k)]
    return en[:4] or ["mystery", "thriller", "suspense", "dark"]


def music_prompt(novel: Novel, keywords: list[str]) -> str:
    mood = ", ".join(_english_mood(keywords))
    return (
        f"Instrumental cinematic underscore for a thriller novel titled '{novel.title}'. "
        f"Mood: {mood}. Dark ambient storytelling bed, tense piano or soft strings, "
        f"no vocals, no lyrics, no pop melody, seamless looping background music."
    )


def generate_novel_music(
    novel: Novel,
    keywords: list[str],
    output: Path,
    config: AppConfig,
    logger: PipelineLogger,
) -> Path | None:
    """Generate instrumental BGM once via ElevenLabs Music API. Cached at `output`."""
    api_key = (config.elevenlabs_api_key or "").strip()
    if not api_key:
        logger.warn("elevenlabs_audio", "ELEVENLABS_API_KEY missing — skip music generation")
        return None

    length_ms = max(10_000, min(int(config.elevenlabs_music_length_ms), 60_000))
    prompt = music_prompt(novel, keywords)
    logger.start("elevenlabs_audio", f"music for '{novel.title}' ({length_ms}ms)")

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "prompt": prompt,
        "music_length_ms": length_ms,
        "force_instrumental": True,
        "model_id": config.elevenlabs_music_model or "music_v1",
    }

    audio = _post_audio(_MUSIC_URL, headers, body, logger, timeout=180)
    if not audio:
        return None

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)
    _write_meta(
        output,
        novel,
        source="elevenlabs_music",
        prompt=prompt,
        extra={"music_length_ms": length_ms},
    )
    logger.ok("elevenlabs_audio", f"music -> {output.name} ({len(audio)} bytes)")
    return output


def generate_novel_sfx(
    novel: Novel,
    keywords: list[str],
    sfx_dir: Path,
    config: AppConfig,
    logger: PipelineLogger,
) -> Path | None:
    """Generate hook/whoosh/cliffhanger SFX once into `sfx_dir`. Reused every episode."""
    api_key = (config.elevenlabs_api_key or "").strip()
    if not api_key:
        logger.warn("elevenlabs_audio", "ELEVENLABS_API_KEY missing — skip SFX generation")
        return None

    sfx_dir.mkdir(parents=True, exist_ok=True)
    mood = ", ".join(_english_mood(keywords))
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    generated: list[str] = []
    for sfx_type, filename in SFX_FILES.items():
        out = sfx_dir / filename
        if out.exists() and out.stat().st_size > 500:
            generated.append(filename)
            continue

        base_prompt, duration = _SFX_PROMPTS[sfx_type]
        prompt = f"{base_prompt}. Thriller mood: {mood}. Novel: {novel.title}."
        logger.start("elevenlabs_audio", f"sfx {sfx_type} for '{novel.title}'")

        body = {
            "text": prompt,
            "duration_seconds": duration,
            "prompt_influence": 0.4,
            "model_id": "eleven_text_to_sound_v2",
        }
        audio = _post_audio(_SOUND_URL, headers, body, logger, timeout=90)
        if not audio:
            logger.warn("elevenlabs_audio", f"sfx {sfx_type} failed — aborting novel SFX set")
            return None

        tmp_mp3 = sfx_dir / f".{sfx_type}.mp3"
        tmp_mp3.write_bytes(audio)
        try:
            _transcode_to_wav(tmp_mp3, out)
        finally:
            tmp_mp3.unlink(missing_ok=True)
        generated.append(filename)
        logger.ok("elevenlabs_audio", f"sfx {sfx_type} -> {out.name} ({out.stat().st_size} bytes)")

    meta = sfx_dir / "sfx.json"
    meta.write_text(
        json.dumps(
            {
                "novel": novel.title,
                "source": "elevenlabs_sfx",
                "files": generated,
                "mood": mood,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return sfx_dir


def novel_sfx_complete(sfx_dir: Path) -> bool:
    if not sfx_dir.exists():
        return False
    return all((sfx_dir / name).exists() and (sfx_dir / name).stat().st_size > 500 for name in SFX_FILES.values())


def _post_audio(
    url: str,
    headers: dict[str, str],
    body: dict,
    logger: PipelineLogger,
    *,
    timeout: int,
) -> bytes | None:
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as exc:
            wait = _RETRY_BASE_SEC * (2 ** attempt)
            logger.warn("elevenlabs_audio", f"connection error — retry in {wait}s ({exc})")
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
                continue
            return None

        if resp.status_code == 200 and resp.content:
            return resp.content

        detail = ""
        try:
            detail = resp.json().get("detail", {})
            if isinstance(detail, dict):
                detail = detail.get("message") or str(detail)
            detail = str(detail)[:300]
        except (ValueError, AttributeError):
            detail = (resp.text or "")[:300]

        if resp.status_code in (401, 402, 403):
            logger.warn("elevenlabs_audio", f"auth/plan error {resp.status_code}: {detail}")
            return None
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = _RETRY_BASE_SEC * (2 ** attempt)
            logger.warn(
                "elevenlabs_audio",
                f"{resp.status_code} — retry in {wait}s ({detail})",
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
                continue
            return None

        logger.warn("elevenlabs_audio", f"HTTP {resp.status_code}: {detail}")
        return None
    return None


def _transcode_to_wav(src: Path, dest: Path) -> None:
    import subprocess

    cmd = [
        get_ffmpeg_exe(),
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "44100",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not dest.exists():
        raise RuntimeError(f"SFX wav convert failed: {result.stderr[-800:]}")


def _write_meta(
    output: Path,
    novel: Novel,
    *,
    source: str,
    prompt: str = "",
    extra: dict | None = None,
) -> None:
    payload = {
        "novel": novel.title,
        "source": source,
        "prompt": prompt,
        "title": f"ElevenLabs {source}",
    }
    if extra:
        payload.update(extra)
    output.with_suffix(".json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
