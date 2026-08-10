"""Per-novel storytelling BGM — cinematic/instrumental only (never pop songs)."""

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
_MIN_ACCEPT_SCORE = 8

# Storytelling / underscore only — NOT EDM drops or pop hits
_PREFERRED_MARKERS = (
    "cinematic",
    "soundtrack",
    "underscore",
    "instrumental",
    "ambient",
    "dark piano",
    "mystery",
    "suspense",
    "thriller",
    "horror",
    "dramatic",
    "epic trailer",
    "storytelling",
    "background music",
    "bgm",
    "no vocals",
    "no copyright",
    "royalty free",
    "free to use",
)

# Hard reject: pop songs, vocals, famous hits (e.g. Faded)
_AVOID_MARKERS = (
    "faded",
    "alan walker",
    "the weeknd",
    "billie eilish",
    "taylor swift",
    "ed sheeran",
    "drake",
    "ariana",
    "bts",
    "lyrics",
    "lyric",
    "official music video",
    "official video",
    "mv",
    "vocal",
    "vocals",
    "singing",
    "cover",
    "karaoke",
    "remix",
    "nightcore",
    "sped up",
    "slowed",
    "tiktok",
    "1 hour",
    "10 hours",
    "mix",
    "playlist",
    "live",
    "concert",
    "radio edit",
    "feat.",
    "ft.",
    "featuring",
)


def fetch_novel_bgm(
    novel: Novel,
    keywords: list[str],
    output: Path,
    logger: PipelineLogger,
    library_dir: Path | None = None,
) -> Path | None:
    """Search and download cinematic storytelling BGM. Cached at `output`."""
    meta = output.with_suffix(".json")
    if output.exists() and meta.exists():
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
            if info.get("source") != "synthetic" and output.stat().st_size > _SYNTHETIC_MAX_BYTES:
                title = (info.get("title") or "").lower()
                if title and any(bad in title for bad in _AVOID_MARKERS):
                    logger.warn("bgm", f"rejecting cached pop/song track: {info.get('title')}")
                    output.unlink(missing_ok=True)
                    meta.unlink(missing_ok=True)
                else:
                    return output
        except (json.JSONDecodeError, OSError):
            pass

    query = _build_search_query(novel, keywords)
    logger.start("bgm", f"searching storytelling BGM for '{novel.title}': {query}")

    url, track_title = _search_storytelling_track(query, logger)
    if not url:
        fallback = _build_fallback_query(keywords)
        logger.info(f"Retrying BGM search: {fallback}")
        url, track_title = _search_storytelling_track(fallback, logger)

    if url and _download_from_youtube(url, output, logger):
        _write_meta(output, novel, query, url, source="youtube", title=track_title)
        logger.ok("bgm", f"{output.name} ({track_title or 'untitled'})")
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
        and not any(bad in p.stem.lower() for bad in _AVOID_MARKERS)
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
    return en or ["mystery", "thriller", "suspense", "dark"]


def _build_search_query(novel: Novel, keywords: list[str]) -> str:
    """Prefer mood + storytelling terms — never chase chart songs."""
    mood = _english_keywords(keywords)[:3]
    parts = [
        "cinematic",
        "instrumental",
        "soundtrack",
        "no vocals",
        "royalty free",
        "dark",
        "mystery",
        "suspense",
    ] + mood
    return " ".join(dict.fromkeys(p.lower() for p in parts))


def _build_fallback_query(keywords: list[str]) -> str:
    mood = _english_keywords(keywords)[:2]
    return " ".join(
        ["dark cinematic underscore instrumental storytelling bgm no vocals"] + mood
    )


def _write_meta(
    output: Path,
    novel: Novel,
    query: str,
    url: str = "",
    source: str = "youtube",
    title: str = "",
) -> None:
    meta = output.with_suffix(".json")
    meta.write_text(
        json.dumps(
            {
                "novel": novel.title,
                "search": query,
                "url": url,
                "source": source,
                "title": title,
            },
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


def _search_storytelling_track(query: str, logger: PipelineLogger) -> tuple[str | None, str]:
    if not _ytdlp_available():
        logger.warn("bgm", "yt-dlp not available — pip install yt-dlp")
        return None, ""

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": "ytsearch10",
        "socket_timeout": 30,
    }

    search_queries = (
        query,
        f"cinematic mystery thriller instrumental soundtrack {query}",
        "dark cinematic storytelling underscore instrumental no vocals royalty free",
        "suspense thriller ambient piano bgm instrumental free to use",
    )

    for search_q in search_queries:
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch8:{search_q}", download=False)
        except Exception as exc:
            logger.warn("bgm", f"search '{search_q[:50]}': {exc}")
            continue

        picked = _pick_best_entry(info.get("entries") or [], logger)
        if picked:
            return picked
    return None, ""


def _pick_best_entry(entries: list, logger: PipelineLogger) -> tuple[str, str] | None:
    scored: list[tuple[int, str, str]] = []

    for entry in entries:
        if not entry:
            continue
        vid_id = entry.get("id")
        title = (entry.get("title") or "").strip()
        title_l = title.lower()
        if not vid_id or not title_l:
            continue

        if any(bad in title_l for bad in _AVOID_MARKERS):
            logger.info(f"bgm | skip song/vocal: {title[:60]}")
            continue

        score = 0
        for good in _PREFERRED_MARKERS:
            if good in title_l:
                score += 4
        if "instrumental" in title_l or "no vocal" in title_l:
            score += 6
        if "soundtrack" in title_l or "underscore" in title_l or "cinematic" in title_l:
            score += 5
        if "background music" in title_l or title_l.endswith(" bgm") or " bgm " in title_l:
            score += 5
        if "ncs" in title_l and "cinematic" not in title_l and "epic" not in title_l:
            # Plain NCS often = dance/pop drops — demote hard
            score -= 6

        if score >= _MIN_ACCEPT_SCORE:
            scored.append((score, vid_id, title))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    logger.info(f"bgm | picked (score={best[0]}): {best[2][:70]}")
    return f"https://www.youtube.com/watch?v={best[1]}", best[2]


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
    base_freq = 900 + (seed % 400)  # 900–1300 Hz anchor
    freqs = (base_freq, min(base_freq + 800, 2200), min(base_freq + 1500, 3000))
    noise = "brown" if seed % 2 else "pink"
    _generate_ambient_track(output, freqs, noise)


def _generate_ambient_track(output: Path, freqs: tuple[int, ...], noise_color: str) -> None:
    duration = _DURATION_SEC
    ffmpeg = get_ffmpeg_exe()

    inputs = [
        "-f", "lavfi", "-i",
        f"anoisesrc=color={noise_color}:duration={duration}:sample_rate=44100:amplitude=0.1",
    ]
    # Band-pass noise into mid-range so the pad survives voice+BGM mix on CI
    filters: list[str] = ["[0:a]highpass=f=800,lowpass=f=2800,volume=0.06[noise]"]
    mix_inputs = ["[noise]"]

    for i, freq in enumerate(freqs):
        if freq <= 0:
            continue
        idx = i + 1
        clamped = max(500, min(freq, 3000))
        inputs.extend([
            "-f", "lavfi", "-i",
            f"sine=frequency={clamped}:duration={duration}:sample_rate=44100",
        ])
        vol = 0.45 - i * 0.06
        filters.append(f"[{idx}:a]volume={vol}[s{idx}]")
        mix_inputs.append(f"[s{idx}]")

    n = len(mix_inputs)
    filter_complex = (
        ";".join(filters)
        + f";{''.join(mix_inputs)}amix=inputs={n}:duration=first,"
        + "volume=1.8,alimiter=limit=0.95,"
        + f"afade=t=in:st=0:d=3,afade=t=out:st={duration - 5}:d=5"
    )

    cmd = [
        ffmpeg, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-c:a", "libmp3lame", "-q:a", "4", str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
