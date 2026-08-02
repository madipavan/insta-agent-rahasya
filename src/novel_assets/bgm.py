"""Per-novel epic BGM — search YouTube by novel mood/keywords, download once, reuse."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.book_queue.models import Novel
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe

_DURATION_SEC = 180
_SYNTHETIC_MAX_BYTES = 900_000
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")

_PREFERRED_MARKERS = ("ncs", "no copyright", "nocopyrightsounds", "royalty free", "epic", "cinematic")
_AVOID_MARKERS = ("vocal cover", "lyrics", "1 hour", "10 hours", "mix", "playlist", "live")


def fetch_novel_bgm(
    novel: Novel,
    keywords: list[str],
    output: Path,
    logger: PipelineLogger,
    library_dir: Path | None = None,
) -> Path | None:
    """Search and download epic BGM tailored to this novel. Cached at `output`."""
    meta = output.with_suffix(".json")
    if output.exists() and meta.exists():
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
            if info.get("source") != "synthetic" and output.stat().st_size > _SYNTHETIC_MAX_BYTES:
                return output
        except (json.JSONDecodeError, OSError):
            pass

    query = _build_search_query(novel, keywords)
    logger.start("bgm", f"searching for '{novel.title}': {query}")

    url = _search_epic_track(query, logger)
    if not url:
        fallback = _build_fallback_query(keywords)
        logger.info(f"Retrying BGM search: {fallback}")
        url = _search_epic_track(fallback, logger)

    if url and _download_from_youtube(url, output, logger):
        _write_meta(output, novel, query, url, source="youtube")
        logger.ok("bgm", output.name)
        return output

    if library_dir and _copy_library_track(novel, library_dir, output, logger):
        _write_meta(output, novel, query, source="library")
        logger.ok("bgm", f"library track -> {output.name}")
        return output

    logger.warn("bgm", f"YouTube/library unavailable for '{novel.title}' — generating mood pad")
    try:
        _generate_novel_pad(output, novel)
        _write_meta(output, novel, query, source="synthetic")
        return output
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warn("bgm", f"BGM fallback failed: {exc}")
        return None


def is_synthetic_bgm(bgm_path: Path) -> bool:
    meta = bgm_path.with_suffix(".json")
    if not meta.exists():
        return bgm_path.exists() and bgm_path.stat().st_size <= _SYNTHETIC_MAX_BYTES
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("source") == "synthetic"
    except (json.JSONDecodeError, OSError):
        return False


def _copy_library_track(novel: Novel, library_dir: Path, output: Path, logger: PipelineLogger) -> bool:
    tracks = sorted(
        p for p in library_dir.glob("*.mp3")
        if p.stat().st_size > _SYNTHETIC_MAX_BYTES
    )
    if not tracks:
        return False
    pick = tracks[novel.id % len(tracks)]
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pick, output)
    logger.info(f"Using library BGM: {pick.name}")
    return True


def _english_keywords(keywords: list[str]) -> list[str]:
    en = [k.strip() for k in keywords if k and not _DEVANAGARI.search(k)]
    return en or ["mystery", "thriller", "suspense", "spy", "dark"]


def _build_search_query(novel: Novel, keywords: list[str]) -> str:
    title_words = [w for w in novel.title.split() if len(w) > 3 and not _DEVANAGARI.search(w)][:2]
    mood = _english_keywords(keywords)[:4]
    parts = ["NCS", "epic", "cinematic"] + mood + title_words
    return " ".join(dict.fromkeys(p.lower() for p in parts))


def _build_fallback_query(keywords: list[str]) -> str:
    mood = _english_keywords(keywords)[:3]
    return " ".join(["epic", "cinematic", "no copyright", "NCS"] + mood)


def _write_meta(
    output: Path, novel: Novel, query: str, url: str = "", source: str = "youtube"
) -> None:
    meta = output.with_suffix(".json")
    meta.write_text(
        json.dumps(
            {"novel": novel.title, "search": query, "url": url, "source": source},
            indent=2,
        ),
        encoding="utf-8",
    )


def _ytdlp_available() -> bool:
    if shutil.which("yt-dlp"):
        return True
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        return False


def _search_epic_track(query: str, logger: PipelineLogger) -> str | None:
    if not _ytdlp_available():
        logger.warn("bgm", "yt-dlp not available — pip install yt-dlp")
        return None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": "ytsearch8",
        "socket_timeout": 30,
    }

    for search_q in (query, f"ncs {query}", f"epic cinematic {query}"):
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch5:{search_q}", download=False)
        except Exception as exc:
            logger.warn("bgm", f"search '{search_q[:40]}': {exc}")
            continue

        url = _pick_best_entry(info.get("entries") or [])
        if url:
            return url

    return None


def _pick_best_entry(entries: list) -> str | None:
    scored: list[tuple[int, str]] = []

    for entry in entries:
        if not entry:
            continue
        vid_id = entry.get("id")
        title = (entry.get("title") or "").lower()
        if not vid_id:
            continue
        if any(bad in title for bad in _AVOID_MARKERS):
            continue

        score = 0
        if any(good in title for good in _PREFERRED_MARKERS):
            score += 10
        if "epic" in title or "cinematic" in title or "dramatic" in title:
            score += 5
        if "ncs" in title or "no copyright" in title:
            score += 8
        scored.append((score, vid_id))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return f"https://www.youtube.com/watch?v={scored[0][1]}"


def _download_from_youtube(url: str, output: Path, logger: PipelineLogger) -> bool:
    ytdlp_bin = shutil.which("yt-dlp")
    if not ytdlp_bin:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            logger.warn("bgm", "yt-dlp not available — pip install yt-dlp")
            return False

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="bgm_dl_"))
    tmp_template = str(tmp_dir / "track.%(ext)s")

    try:
        if ytdlp_bin:
            subprocess.run(
                [
                    ytdlp_bin, "--no-playlist", "--extract-audio",
                    "--audio-format", "mp3", "--audio-quality", "192K",
                    "--output", tmp_template, "--no-warnings", "--quiet", url,
                ],
                check=True, capture_output=True, timeout=180,
            )
        else:
            import yt_dlp
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": tmp_template,
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        downloaded = list(tmp_dir.glob("track.*"))
        if not downloaded:
            return False

        if output.exists():
            output.unlink()
        shutil.move(str(downloaded[0]), str(output))
        return output.exists() and output.stat().st_size > _SYNTHETIC_MAX_BYTES

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warn("bgm", f"download failed: {exc}")
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _generate_novel_pad(output: Path, novel: Novel) -> None:
    seed = int(hashlib.md5(novel.title.encode()).hexdigest()[:8], 16)
    base_freq = 45 + (seed % 20)
    freqs = (base_freq, int(base_freq * 1.5), int(base_freq * 2))
    noise = "brown" if seed % 2 else "pink"
    _generate_ambient_track(output, freqs, noise)


def _generate_ambient_track(output: Path, freqs: tuple[int, ...], noise_color: str) -> None:
    duration = _DURATION_SEC
    ffmpeg = get_ffmpeg_exe()

    inputs = [
        "-f", "lavfi", "-i",
        f"anoisesrc=color={noise_color}:duration={duration}:sample_rate=44100:amplitude=0.06",
    ]
    filters: list[str] = ["[0:a]lowpass=f=500[noise]"]
    mix_inputs = ["[noise]"]

    for i, freq in enumerate(freqs):
        if freq <= 0:
            continue
        idx = i + 1
        inputs.extend(["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}:sample_rate=44100"])
        vol = 0.12 - i * 0.02
        filters.append(f"[{idx}:a]volume={vol}[s{idx}]")
        mix_inputs.append(f"[s{idx}]")

    n = len(mix_inputs)
    filter_complex = (
        ";".join(filters)
        + f";{''.join(mix_inputs)}amix=inputs={n}:duration=first,"
        + f"afade=t=in:st=0:d=3,afade=t=out:st={duration - 5}:d=5"
    )

    cmd = [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-c:a", "libmp3lame", "-q:a", "4", str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
