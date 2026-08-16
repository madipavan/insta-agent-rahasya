"""Hybrid stock footage resolver — Replicate fiction stills, local library, Pixabay, Pexels."""

from __future__ import annotations

import random
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import requests
from PIL import Image

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.visuals.replicate_art import ReplicateArtClient


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
        self.replicate = ReplicateArtClient(config, logger, self.cache_path)

    def resolve_visuals(self, keywords: list[str], output_dir: Path) -> list[Path]:
        """Return montage assets — Replicate stills-only when configured, else hybrid stock."""
        clean_kw = [k for k in keywords if isinstance(k, str) and k.lower() not in ("esmodule", "module")]
        if not clean_kw:
            clean_kw = ["mystery", "thriller", "cinematic"]

        art_cfg = getattr(self.config, "replicate_art", None)
        prefer_stills = bool(getattr(art_cfg, "prefer_stills_only", True))
        still_count = int(getattr(art_cfg, "reel_still_count", 6) or 6)

        if prefer_stills and self.replicate.available:
            self.logger.start(
                "stock",
                f"{', '.join(clean_kw[:4])} | replicate stills-only ×{still_count}",
            )
            stills = self._generate_replicate_stills(clean_kw, still_count)
            if stills:
                self.logger.ok("stock", f"{len(stills)} Replicate stills (full reel)")
                return stills
            self.logger.warn("stock", "Replicate stills-only failed — falling back to hybrid stock")

        video_count = self.config.video.clip_count
        photo_count = self.config.video.photo_count
        providers = [p.lower() for p in self.config.video.stock_providers]
        self.logger.start(
            "stock",
            f"{', '.join(clean_kw[:4])} | {video_count}v + {photo_count}p | {'→'.join(providers)}",
        )

        visuals: list[Path] = []

        if "local" in providers:
            for keyword in clean_kw:
                local = self._find_local(keyword)
                if local and local not in visuals:
                    visuals.append(local)
                if len(visuals) >= video_count:
                    break
            if len(visuals) < video_count:
                for path in self._find_local_any(video_count - len(visuals)):
                    if path not in visuals:
                        visuals.append(path)

        if len(visuals) < video_count and any(p in providers for p in ("pixabay", "pexels")):
            queries = self._build_queries(clean_kw)
            for query in queries:
                needed = video_count - len(visuals)
                for path in self._fetch_remote_videos(query, needed, providers):
                    if path not in visuals:
                        visuals.append(path)
                    if len(visuals) >= video_count:
                        break
                if len(visuals) >= video_count:
                    break

        photos: list[Path] = []
        if photo_count > 0:
            while len(photos) < photo_count and self.replicate.available:
                art = self.replicate.generate_photo(
                    clean_kw + [f"scene{len(photos) + 1}"],
                    width=self.config.video.width,
                    height=self.config.video.height,
                )
                if not art or art in photos:
                    break
                photos.append(art)

            if len(photos) < photo_count:
                for query in self._build_queries(clean_kw, artistic=True):
                    photo = self._fetch_remote_photo(query, providers)
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

    def _generate_replicate_stills(self, keywords: list[str], count: int) -> list[Path]:
        """Generate unique fictional stills for a full-reel Ken Burns montage."""
        import time

        if count <= 0 or not self.replicate.available:
            return []
        stills: list[Path] = []
        for i in range(count):
            # Put salts first so they are never truncated from the T2I prompt
            salted = [f"scene{i + 1}", f"beat{i + 1}"] + list(keywords)
            art = self.replicate.generate_photo(
                salted,
                width=self.config.video.width,
                height=self.config.video.height,
            )
            if art and art not in stills:
                stills.append(art)
            elif not art:
                # Wait for free-tier rate limit, then one retry
                time.sleep(12)
                art = self.replicate.generate_photo(
                    [f"scene{i + 1}", f"variant{i + 1}", f"shot{i + 1}"] + list(keywords),
                    width=self.config.video.width,
                    height=self.config.video.height,
                )
                if art and art not in stills:
                    stills.append(art)
                else:
                    break
            # Pace free-tier: ~6/min with burst 1
            if i + 1 < count:
                time.sleep(11)
        min_ok = max(2, (count + 1) // 2)
        if len(stills) < min_ok:
            return []
        return stills

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

    def _find_local_any(self, limit: int) -> list[Path]:
        if limit <= 0 or not self.library_path.exists():
            return []
        clips = list(self.library_path.glob("**/*.mp4")) + list(self.library_path.glob("**/*.mov"))
        random.shuffle(clips)
        return clips[:limit]

    def _fetch_remote_videos(
        self, query: str, limit: int, providers: list[str]
    ) -> list[Path]:
        if limit <= 0:
            return []
        fetchers: list[Callable[[str, int], list[Path]]] = []
        if "pixabay" in providers:
            fetchers.append(self._fetch_pixabay_videos)
        if "pexels" in providers:
            fetchers.append(self._fetch_pexels_videos)

        results: list[Path] = []
        for fetch in fetchers:
            for path in fetch(query, limit - len(results)):
                if path not in results:
                    results.append(path)
                if len(results) >= limit:
                    return results
        return results

    def _fetch_remote_photo(self, query: str, providers: list[str]) -> Path | None:
        if "pixabay" in providers:
            photo = self._fetch_pixabay_photo_file(query)
            if photo:
                return photo
        if "pexels" in providers:
            return self._fetch_pexels_photo_file(query)
        return None

    def _fetch_pixabay_videos(self, query: str, limit: int) -> list[Path]:
        if not self.config.pixabay_api_key or limit <= 0:
            return []
        try:
            resp = requests.get(
                "https://pixabay.com/api/videos/",
                params={
                    "key": self.config.pixabay_api_key,
                    "q": query,
                    "per_page": min(limit + 3, 20),
                    "video_type": "film",
                },
                timeout=30,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except requests.RequestException as exc:
            self.logger.warn("stock", f"Pixabay video failed: {exc}")
            return []

        random.shuffle(hits)
        results: list[Path] = []
        for hit in hits:
            if len(results) >= limit:
                break
            path = self._download_pixabay_video(hit)
            if path:
                results.append(path)
        return results

    def _download_pixabay_video(self, hit: dict) -> Path | None:
        videos = hit.get("videos", {})
        for quality in ("large", "medium", "small", "tiny"):
            url = videos.get(quality, {}).get("url")
            if url:
                break
        else:
            return None
        vid_id = hit.get("id", random.randint(1, 99999))
        out = self.cache_path / f"pixabay_{vid_id}.mp4"
        if out.exists():
            return out
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            out.write_bytes(r.content)
            return out
        except requests.RequestException:
            return None

    def _fetch_pixabay_photo_file(self, query: str) -> Path | None:
        if not self.config.pixabay_api_key:
            return None
        try:
            resp = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": self.config.pixabay_api_key,
                    "q": query,
                    "per_page": 12,
                    "orientation": "vertical",
                    "image_type": "photo",
                },
                timeout=30,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
        except requests.RequestException as exc:
            self.logger.warn("stock", f"Pixabay photo failed: {exc}")
            return None

        random.shuffle(hits)
        for hit in hits:
            url = hit.get("largeImageURL") or hit.get("webformatURL")
            if not url:
                continue
            out = self.cache_path / f"pixabay_photo_{hit.get('id', 0)}.jpg"
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

    def fetch_photo(
        self,
        keywords: list[str],
        width: int,
        height: int,
        *,
        novel_title: str | None = None,
    ) -> Image.Image | None:
        art_path = self.replicate.generate_photo(
            keywords,
            width=width,
            height=height,
            novel_title=novel_title,
        )
        if art_path:
            return Image.open(art_path).convert("RGB")

        providers = [p.lower() for p in self.config.video.stock_providers]
        query = " ".join(keywords[:3]) + " dark cinematic artistic"
        path = self._fetch_remote_photo(query, providers)
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
