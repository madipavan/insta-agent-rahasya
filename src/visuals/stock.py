"""Hybrid stock footage resolver — multiple videos + artistic photos."""

from __future__ import annotations

import random
import subprocess
import tempfile
from pathlib import Path

import requests
from PIL import Image

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe


class StockResolver:
    ARTISTIC_SUFFIXES = [
        "cinematic artistic dark",
        "moody oil painting style",
        "noir atmosphere night",
        "dramatic shadows suspense",
    ]

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.library_path = config.path("stock_library")
        self.cache_path = config.path("output_dir") / "stock_cache"
        self.cache_path.mkdir(parents=True, exist_ok=True)

    def resolve_visuals(self, keywords: list[str], output_dir: Path) -> list[Path]:
        """Return multiple clips and photos for montage editing."""
        clean_kw = [k for k in keywords if isinstance(k, str) and k.lower() not in ("esmodule", "module")]
        if not clean_kw:
            clean_kw = ["mystery", "thriller", "cinematic"]

        video_count = self.config.video.clip_count
        photo_count = self.config.video.photo_count
        self.logger.start("stock", f"{', '.join(clean_kw[:4])} | {video_count}v + {photo_count}p")

        visuals: list[Path] = []

        for keyword in clean_kw:
            local = self._find_local(keyword)
            if local and local not in visuals:
                visuals.append(local)
            if len(visuals) >= video_count:
                break

        if len(visuals) < video_count:
            queries = self._build_queries(clean_kw)
            for query in queries:
                for path in self._fetch_pexels_videos(query, video_count - len(visuals)):
                    if path not in visuals:
                        visuals.append(path)
                    if len(visuals) >= video_count:
                        break
                if len(visuals) >= video_count:
                    break

        photos: list[Path] = []
        if photo_count > 0:
            for query in self._build_queries(clean_kw, artistic=True):
                photo = self._fetch_pexels_photo_file(query)
                if photo and photo not in photos:
                    photos.append(photo)
                if len(photos) >= photo_count:
                    break

        if not visuals and not photos:
            placeholder = self._create_placeholder(output_dir)
            self.logger.warn("stock", "using placeholder")
            return [placeholder]

        montage = self._interleave(visuals[:video_count], photos[:photo_count])
        self.logger.ok("stock", f"{len(montage)} clips ({len(visuals)} video, {len(photos)} photo)")
        return montage

    def resolve(self, keywords: list[str], output_dir: Path) -> Path:
        """Single-clip fallback for static post frame extraction."""
        visuals = self.resolve_visuals(keywords, output_dir)
        for v in visuals:
            if v.suffix.lower() in (".mp4", ".mov", ".webm"):
                return v
        return visuals[0]

    def _build_queries(self, keywords: list[str], artistic: bool = False) -> list[str]:
        base = " ".join(keywords[:3])
        queries = [f"{base} dark moody cinematic"]
        if self.config.video.artistic_stock or artistic:
            for suffix in self.ARTISTIC_SUFFIXES:
                queries.append(f"{base} {suffix}")
        return queries

    def _interleave(self, videos: list[Path], photos: list[Path]) -> list[Path]:
        """Mix videos and photos: V P V P V P pattern."""
        result: list[Path] = []
        vi, pi = 0, 0
        while vi < len(videos) or pi < len(photos):
            if vi < len(videos):
                result.append(videos[vi])
                vi += 1
            if pi < len(photos):
                result.append(photos[pi])
                pi += 1
        return result

    def _find_local(self, keyword: str) -> Path | None:
        keyword_dir = self.library_path / keyword.lower().replace(" ", "_")
        if not keyword_dir.exists():
            return None
        clips = list(keyword_dir.glob("*.mp4")) + list(keyword_dir.glob("*.mov"))
        if clips:
            return random.choice(clips)
        return None

    def _fetch_pexels_videos(self, query: str, limit: int) -> list[Path]:
        if not self.config.pexels_api_key or limit <= 0:
            return []
        headers = {"Authorization": self.config.pexels_api_key}
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": query, "per_page": min(limit + 3, 15), "orientation": "portrait"},
                timeout=30,
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
        except requests.RequestException as exc:
            self.logger.warn("stock", f"Pexels video failed: {exc}")
            return []

        random.shuffle(videos)
        results: list[Path] = []
        for video in videos:
            if len(results) >= limit:
                break
            path = self._download_pexels_video(video)
            if path:
                results.append(path)
        return results

    def _download_pexels_video(self, video: dict) -> Path | None:
        files = video.get("video_files", [])
        best = None
        for f in files:
            if f.get("width", 0) >= 720:
                best = f
                break
        if not best and files:
            best = files[0]
        if not best:
            return None
        url = best.get("link")
        if not url:
            return None
        vid_id = video.get("id", random.randint(1, 99999))
        out = self.cache_path / f"pexels_{vid_id}.mp4"
        if out.exists():
            return out
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            out.write_bytes(r.content)
            return out
        except requests.RequestException:
            return None

    def _fetch_pexels_photo_file(self, query: str) -> Path | None:
        if not self.config.pexels_api_key:
            return None
        headers = {"Authorization": self.config.pexels_api_key}
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                headers=headers,
                params={"query": query, "per_page": 10, "orientation": "portrait"},
                timeout=30,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
        except requests.RequestException:
            return None

        random.shuffle(photos)
        for photo in photos:
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")
            if not url:
                continue
            out = self.cache_path / f"pexels_photo_{photo.get('id', 0)}.jpg"
            if out.exists():
                return out
            try:
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                out.write_bytes(r.content)
                return out
            except requests.RequestException:
                continue
        return None

    def _create_placeholder(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "placeholder_bg.png"
        img = Image.new("RGB", (self.config.video.width, self.config.video.height), "#0A0E1A")
        img.save(path)
        return path

    def fetch_photo(self, keywords: list[str], width: int, height: int) -> Image.Image | None:
        path = self._fetch_pexels_photo_file(" ".join(keywords[:3]) + " dark cinematic artistic")
        if path:
            return Image.open(path).convert("RGB")
        return None

    def extract_video_frame(self, video_path: Path, at_sec: float = 2.0) -> Image.Image | None:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            frame_path = Path(tmp.name)
        try:
            result = subprocess.run(
                [
                    get_ffmpeg_exe(), "-y", "-ss", str(at_sec), "-i", str(video_path),
                    "-vframes", "1", "-q:v", "2", str(frame_path),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return None
            return Image.open(frame_path).convert("RGB")
        except OSError:
            return None
        finally:
            frame_path.unlink(missing_ok=True)
