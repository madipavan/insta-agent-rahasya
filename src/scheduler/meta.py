"""Meta (Instagram) Graph API — direct reel + carousel publishing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.post_details import PostDetails


@dataclass
class MetaPostResult:
    reel_container_id: str
    reel_publish_id: str | None
    carousel_container_id: str | None
    carousel_publish_id: str | None
    scheduled_reel_at: str
    scheduled_carousel_at: str

    def summary(self) -> str:
        parts = [f"reel:{self.reel_container_id}"]
        if self.reel_publish_id:
            parts.append(f"reel_pub:{self.reel_publish_id}")
        if self.carousel_container_id:
            parts.append(f"carousel:{self.carousel_container_id}")
        if self.carousel_publish_id:
            parts.append(f"carousel_pub:{self.carousel_publish_id}")
        return ";".join(parts)


class MetaScheduler:
    """Publish reels and carousels via Instagram Graph API."""

    GRAPH_URL = "https://graph.facebook.com/v21.0"
    RUPLOAD_URL = "https://rupload.facebook.com/ig-api-upload/v21.0"
    PHOTO_PERMISSIONS = (
        "pages_manage_posts",
        "pages_read_engagement",
        "pages_show_list",
    )

    POLL_INTERVAL_SEC = 5
    POLL_MAX_ATTEMPTS = 60

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.ig_user_id = (config.meta_ig_user_id or "").strip()
        self.access_token = (config.meta_access_token or "").strip()
        self.page_id = (config.meta_page_id or "").strip()

    def is_configured(self) -> bool:
        token = (self.access_token or "").strip()
        return bool(self.ig_user_id and token and token.startswith("EAA"))

    def queue_posts(
        self,
        reel_path: Path,
        static_paths: list[Path] | Path,
        caption: str,
        bundle_id: str,
        *,
        thumbnail_path: Path | None = None,
        post_details: PostDetails | None = None,
    ) -> str:
        if isinstance(static_paths, Path):
            static_paths = [static_paths]

        self.logger.start("meta", bundle_id)

        if not self.is_configured():
            self.logger.warn("meta", "not configured — saving package for manual upload")
            return self._save_manual_package(
                reel_path, static_paths, caption, bundle_id, thumbnail_path
            )

        try:
            return self._queue_posts_configured(
                reel_path,
                static_paths,
                caption,
                bundle_id,
                thumbnail_path=thumbnail_path,
                post_details=post_details,
            )
        except (requests.RequestException, RuntimeError, TimeoutError) as exc:
            self.logger.warn("meta", f"API failed ({exc}) — saving package for manual upload")
            return self._save_manual_package(
                reel_path, static_paths, caption, bundle_id, thumbnail_path
            )

    def _queue_posts_configured(
        self,
        reel_path: Path,
        static_paths: list[Path],
        caption: str,
        bundle_id: str,
        *,
        thumbnail_path: Path | None = None,
        post_details: PostDetails | None = None,
    ) -> str:
        reel_caption = post_details.reel_caption if post_details else caption
        carousel_caption = (
            post_details.carousel_caption if post_details else caption
        )

        reel_time = self._next_post_time()
        carousel_time = reel_time + timedelta(minutes=5)

        cover_url = None
        if thumbnail_path and thumbnail_path.exists():
            cover_url = self._upload_cover_image(thumbnail_path)

        reel_container = self._create_reel_container(
            self._prepare_reel_for_instagram(reel_path),
            reel_caption,
            cover_url=cover_url,
            publish_at=reel_time,
        )
        reel_publish_id = self._wait_and_publish(reel_container, publish_at=reel_time)

        carousel_container_id = None
        carousel_publish_id = None
        if static_paths:
            carousel_container_id = self._create_carousel_container(
                static_paths, carousel_caption, publish_at=carousel_time
            )
            carousel_publish_id = self._wait_and_publish(
                carousel_container_id, publish_at=carousel_time
            )

        result = MetaPostResult(
            reel_container_id=reel_container,
            reel_publish_id=reel_publish_id,
            carousel_container_id=carousel_container_id,
            carousel_publish_id=carousel_publish_id,
            scheduled_reel_at=reel_time.isoformat(),
            scheduled_carousel_at=carousel_time.isoformat(),
        )
        self.logger.ok("meta", result.summary())
        return result.summary()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"OAuth {self.access_token}"}

    def _next_post_time(self) -> datetime:
        tz = ZoneInfo(self.config.timezone)
        now = datetime.now(tz)
        hour, minute = map(int, self.config.post_time.split(":"))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)
        # Meta requires publish_at at least 10 minutes in the future
        min_future = now + timedelta(minutes=11)
        if scheduled < min_future:
            scheduled = min_future
        return scheduled

    def _unix_publish_at(self, when: datetime) -> int:
        return int(when.timestamp())

    def _create_reel_container(
        self,
        video_path: Path,
        caption: str,
        *,
        cover_url: str | None = None,
        publish_at: datetime | None = None,
    ) -> str:
        del publish_at
        last_error: Exception | None = None
        for attempt, use_cover in enumerate((bool(cover_url), False), start=1):
            try:
                return self._create_reel_container_once(
                    video_path, caption, cover_url if use_cover else None
                )
            except (requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt == 1 and cover_url:
                    self.logger.warn("meta", f"reel upload with cover failed ({exc}) — retrying without cover")
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("reel container creation failed")

    def _create_reel_container_once(
        self,
        video_path: Path,
        caption: str,
        cover_url: str | None,
    ) -> str:
        params: dict[str, str] = {
            "access_token": self.access_token,
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:2200],
            "share_to_feed": "true",
        }
        if cover_url:
            params["cover_url"] = cover_url

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media",
            params=params,
            timeout=60,
        )
        if resp.status_code >= 400:
            self._log_api_error("reel container", resp)
        resp.raise_for_status()
        body = resp.json()
        container_id = body["id"]
        upload_url = body.get("uri") or f"{self.RUPLOAD_URL}/{container_id}"
        self.logger.info(f"Reel container created: {container_id}")

        self._resumable_upload_binary(container_id, video_path, upload_url=upload_url)
        return container_id

    def _upload_video_to_container(
        self, container_id: str, file_path: Path, upload_url: str | None = None
    ) -> None:
        """Upload reel bytes via rupload (Meta rejects first-party hosted file_url)."""
        self._resumable_upload_binary(container_id, file_path, upload_url=upload_url)

    def _resumable_upload_binary(
        self,
        container_id: str,
        file_path: Path,
        *,
        upload_url: str | None = None,
    ) -> None:
        file_size = file_path.stat().st_size
        if file_size == 0:
            raise RuntimeError(f"Video file is empty: {file_path}")
        if file_size > 100 * 1024 * 1024:
            raise RuntimeError(
                f"Video too large for Instagram upload ({file_size / (1024 * 1024):.1f} MiB)"
            )

        target_url = upload_url or f"{self.RUPLOAD_URL}/{container_id}"
        chunk_size = 4 * 1024 * 1024
        offset = 0
        with open(file_path, "rb") as handle:
            while offset < file_size:
                chunk = handle.read(min(chunk_size, file_size - offset))
                if not chunk:
                    break
                headers = {
                    "Authorization": f"OAuth {self.access_token}",
                    "offset": str(offset),
                    "file_size": str(file_size),
                    "Content-Type": "application/octet-stream",
                }
                resp = requests.post(
                    target_url,
                    headers=headers,
                    data=chunk,
                    timeout=600,
                )
                if resp.status_code >= 400:
                    self._log_api_error("rupload binary", resp)
                    raise RuntimeError(
                        f"rupload failed at offset {offset} ({resp.status_code}): {resp.text[:500]}"
                    )
                offset += len(chunk)

        self.logger.info(f"Uploaded {file_path.name} ({file_size} bytes) via binary rupload")

    def _prepare_reel_for_instagram(self, video_path: Path) -> Path:
        """Re-encode to H.264/AAC + faststart and enforce Instagram's 90s reel cap."""
        import subprocess
        import tempfile

        from src.utils.ffmpeg_path import get_ffmpeg_exe, get_media_duration

        max_sec = float(getattr(self.config.video, "instagram_max_sec", 90))
        out = Path(tempfile.mkstemp(suffix="_ig.mp4")[1])
        cmd = [
            get_ffmpeg_exe(), "-y",
            "-i", str(video_path),
            "-t", str(max_sec),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "24",
            "-profile:v", "main", "-level", "4.0", "-pix_fmt", "yuv420p",
            "-r", "30", "-vsync", "cfr", "-g", "60", "-keyint_min", "60",
            "-maxrate", "2000k", "-bufsize", "4000k",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Instagram video prep failed: {result.stderr[-800:]}")
        final_dur = get_media_duration(out)
        self.logger.info(
            f"meta | prepared reel for upload: {out.stat().st_size} bytes, {final_dur:.1f}s"
        )
        return out

    def _resumable_upload(self, container_id: str, file_path: Path) -> None:
        """Backward-compatible alias."""
        self._upload_video_to_container(container_id, file_path)

    def _wait_and_publish(
        self, container_id: str, *, publish_at: datetime | None = None
    ) -> str | None:
        for attempt in range(self.POLL_MAX_ATTEMPTS):
            resp = requests.get(
                f"{self.GRAPH_URL}/{container_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "status_code,status",
                },
                timeout=30,
            )
            resp.raise_for_status()
            status = resp.json().get("status_code", "")
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError(
                    f"Container {container_id} failed: {resp.json().get('status')}"
                )
            time.sleep(self.POLL_INTERVAL_SEC)
        else:
            raise TimeoutError(f"Container {container_id} did not finish in time")

        params: dict[str, str] = {
            "access_token": self.access_token,
            "creation_id": container_id,
        }
        # Instagram Graph API publishes immediately — scheduling is handled by our publish job.

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media_publish",
            params=params,
            timeout=60,
        )
        if resp.status_code >= 400:
            self._log_api_error("media_publish", resp)
        resp.raise_for_status()
        publish_id = resp.json().get("id", "")
        self.logger.info(f"Published container {container_id} → {publish_id}")
        return publish_id or None

    def _upload_image_container(self, image_path: Path) -> str:
        """Upload a single image as carousel child; returns container ID."""
        image_url = self._upload_image_as_public_url(image_path)
        if not image_url:
            raise RuntimeError(f"Failed to upload carousel image: {image_path.name}")

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media",
            params={
                "access_token": self.access_token,
                "image_url": image_url,
                "is_carousel_item": "true",
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _create_carousel_container(
        self,
        image_paths: list[Path],
        caption: str,
        *,
        publish_at: datetime | None = None,
    ) -> str:
        del publish_at
        child_ids: list[str] = []
        for img_path in image_paths:
            child_id = self._upload_image_container(img_path)
            self._wait_container_ready(child_id)
            child_ids.append(child_id)

        params: dict[str, str] = {
            "access_token": self.access_token,
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption[:2200],
        }

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media",
            params=params,
            timeout=60,
        )
        if resp.status_code >= 400:
            self._log_api_error("carousel container", resp)
        resp.raise_for_status()
        container_id = resp.json()["id"]
        self.logger.info(f"Carousel container created: {container_id} ({len(child_ids)} slides)")
        return container_id

    def _wait_container_ready(self, container_id: str) -> None:
        for _ in range(self.POLL_MAX_ATTEMPTS):
            resp = requests.get(
                f"{self.GRAPH_URL}/{container_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "status_code",
                },
                timeout=30,
            )
            resp.raise_for_status()
            if resp.json().get("status_code") == "FINISHED":
                return
            time.sleep(2)
        raise TimeoutError(f"Image container {container_id} not ready")

    def _upload_cover_image(self, thumbnail_path: Path) -> str | None:
        """Upload thumbnail to Facebook as unpublished photo; return public URL."""
        return self._upload_image_as_public_url(thumbnail_path)

    def _upload_image_as_public_url(self, image_path: Path) -> str | None:
        if not self.page_id:
            self.logger.warn("meta", "META_PAGE_ID missing — cannot host images for API")
            return None
        try:
            with open(image_path, "rb") as f:
                resp = requests.post(
                    f"{self.GRAPH_URL}/{self.page_id}/photos",
                    data={
                        "access_token": self.access_token,
                        "published": "false",
                        "temporary": "true",
                    },
                    files={"source": (image_path.name, f, "image/png")},
                    timeout=60,
                )
            if resp.status_code >= 400:
                self._log_api_error("page photo upload", resp)
                return None
            photo_id = resp.json().get("id")
            if not photo_id:
                return None
            url_resp = requests.get(
                f"{self.GRAPH_URL}/{photo_id}",
                params={"access_token": self.access_token, "fields": "images"},
                timeout=30,
            )
            if url_resp.status_code >= 400:
                self._log_api_error("photo url lookup", url_resp)
                return None
            images = url_resp.json().get("images", [])
            if images:
                return images[0].get("source")
        except requests.RequestException as exc:
            self.logger.warn("meta", f"image upload failed: {exc}")
        return None

    def search_hashtags(self, queries: list[str], limit: int = 10) -> list[str]:
        """Search Instagram hashtags via Graph API; returns ranked tag names."""
        if not self.is_configured():
            return []

        found: list[tuple[int, str]] = []
        seen: set[str] = set()

        for query in queries:
            q = query.lstrip("#").lower()
            if not q or q in seen:
                continue
            try:
                resp = requests.get(
                    f"{self.GRAPH_URL}/ig_hashtag_search",
                    params={
                        "access_token": self.access_token,
                        "user_id": self.ig_user_id,
                        "q": q,
                    },
                    timeout=30,
                )
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("data", []):
                    tag_id = item.get("id")
                    if not tag_id:
                        continue
                    info = requests.get(
                        f"{self.GRAPH_URL}/{tag_id}",
                        params={
                            "access_token": self.access_token,
                            "fields": "name",
                        },
                        timeout=15,
                    )
                    if info.status_code == 200:
                        name = info.json().get("name", "").lower()
                        if name and name not in seen:
                            seen.add(name)
                            found.append((len(found), f"#{name}"))
            except requests.RequestException:
                continue

        return [tag for _, tag in found[:limit]]

    def _save_manual_package(
        self,
        reel_path: Path,
        static_paths: list[Path],
        caption: str,
        bundle_id: str,
        thumbnail_path: Path | None,
    ) -> str:
        import shutil

        package_dir = self.config.path("output_dir") / "ready_to_upload" / bundle_id
        package_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reel_path, package_dir / "reel.mp4")
        if thumbnail_path and thumbnail_path.exists():
            shutil.copy2(thumbnail_path, package_dir / "thumbnail.png")
        for i, sp in enumerate(static_paths):
            shutil.copy2(sp, package_dir / f"static_post_{i + 1:02d}.png")
        if static_paths:
            shutil.copy2(static_paths[0], package_dir / "static_post.png")
        (package_dir / "caption.txt").write_text(caption, encoding="utf-8")
        (package_dir / "UPLOAD_INSTRUCTIONS.txt").write_text(
            "Meta API not configured. Upload manually:\n"
            "1. reel.mp4 as Instagram Reel (use thumbnail.png as cover)\n"
            f"2. static_post_*.png as carousel ({len(static_paths)} slides)\n"
            f"Scheduled time: {self.config.post_time} {self.config.timezone}\n",
            encoding="utf-8",
        )
        return f"manual_package:{bundle_id}"

    def _log_api_error(self, step: str, resp: requests.Response) -> None:
        try:
            detail = resp.json().get("error", {})
            message = detail.get("message", resp.text[:300])
            code = detail.get("code", resp.status_code)
            subcode = detail.get("error_subcode", "")
            self.logger.warn("meta", f"{step} failed [{code}/{subcode}]: {message}")
        except (ValueError, AttributeError):
            self.logger.warn("meta", f"{step} failed: {resp.text[:300]}")

    @staticmethod
    def inspect_token(token: str, app_id: str = "", app_secret: str = "") -> dict:
        """Return token type, app id, and granted scopes from Graph debug_token."""
        token = (token or "").strip()
        if not token:
            return {"ok": False, "error": "No token"}

        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        app_token = f"{app_id}|{app_secret}" if app_id and app_secret else token

        resp = requests.get(
            "https://graph.facebook.com/v21.0/debug_token",
            params={"input_token": token, "access_token": app_token},
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return {"ok": False, "error": err.get("message", resp.text)}

        data = resp.json().get("data", {})
        expires_at = data.get("expires_at")
        expires_label = "never (Page token)" if expires_at == 0 else str(expires_at)
        return {
            "ok": True,
            "type": data.get("type", "?"),
            "app_id": data.get("app_id"),
            "is_valid": data.get("is_valid"),
            "scopes": data.get("scopes", []) or [],
            "expires_at": expires_at,
            "expires_label": expires_label,
        }

    @staticmethod
    def validate_app_credentials(app_id: str, app_secret: str) -> dict:
        """Verify META_APP_ID + META_APP_SECRET pair (client credentials grant)."""
        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        if not app_id or not app_secret:
            return {"ok": False, "error": "META_APP_ID and META_APP_SECRET required"}

        resp = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            msg = err.get("message", resp.text)
            if "client secret" in msg.lower():
                return {
                    "ok": False,
                    "error": (
                        "META_APP_SECRET is wrong for META_APP_ID. "
                        "Copy a fresh App Secret from Meta Developers → Your App → "
                        "App settings → Basic (Show → copy). "
                        "Use the SAME app in Graph API Explorer."
                    ),
                }
            return {"ok": False, "error": msg}
        return {"ok": True, "app_access_token": resp.json().get("access_token", "")}

    @staticmethod
    def exchange_long_lived_user_token(
        short_token: str, app_id: str, app_secret: str
    ) -> dict:
        """Exchange short-lived user token for long-lived user token (~60 days)."""
        short_token = (short_token or "").strip()
        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        if not short_token:
            return {"ok": False, "error": "No user token"}
        if not app_id or not app_secret:
            return {
                "ok": False,
                "error": "META_APP_ID and META_APP_SECRET required in .env for long-lived exchange",
            }

        resp = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return {"ok": False, "error": err.get("message", resp.text)}

        body = resp.json()
        token = body.get("access_token", "")
        if not token:
            return {"ok": False, "error": "No access_token in exchange response"}
        return {
            "ok": True,
            "access_token": token,
            "expires_in": body.get("expires_in"),
        }

    @staticmethod
    def obtain_permanent_page_token(
        short_user_token: str,
        app_id: str,
        app_secret: str,
        page_id: str = "",
    ) -> dict:
        """
        Get a Page access token that does not expire (Meta's standard automation path).

        1. Short user token → long-lived user token (needs app id + secret)
        2. Long-lived user → Page access token (never expires unless revoked)
        """
        exchange = MetaScheduler.exchange_long_lived_user_token(
            short_user_token, app_id, app_secret
        )
        if not exchange["ok"]:
            return exchange

        long_token = exchange["access_token"]
        pages_result = MetaScheduler.discover_accounts(long_token)
        if not pages_result["ok"]:
            return pages_result

        pages = pages_result.get("pages") or []
        target_page_id = (page_id or "").strip()

        chosen: dict | None = None
        if target_page_id:
            for p in pages:
                if p.get("id") == target_page_id:
                    chosen = p
                    break
            if not chosen:
                page_result = MetaScheduler.fetch_page_token(long_token, target_page_id)
                if page_result["ok"]:
                    chosen = {
                        "id": page_result["page"].get("id"),
                        "name": page_result["page"].get("name"),
                        "access_token": page_result["page_token"],
                        "instagram_business_account": None,
                    }
        elif pages:
            chosen = pages[0]

        if not chosen or not chosen.get("access_token"):
            return {
                "ok": False,
                "error": "Could not obtain Page token. Check META_PAGE_ID and Page Admin access.",
            }

        page_token = chosen["access_token"]
        token_info = MetaScheduler.inspect_token(page_token, app_id, app_secret)
        ig = chosen.get("instagram_business_account") or {}

        return {
            "ok": True,
            "page_id": chosen.get("id"),
            "page_name": chosen.get("name"),
            "page_token": page_token,
            "ig_user_id": ig.get("id"),
            "ig_username": ig.get("username"),
            "token_info": token_info,
            "long_lived_user_expires_in": exchange.get("expires_in"),
        }

    @staticmethod
    def probe_photo_upload(config: AppConfig) -> dict:
        """Try uploading a tiny PNG to the Page (carousel + cover need this)."""
        token = (config.meta_access_token or "").strip()
        page_id = (config.meta_page_id or "").strip()
        if not token or not page_id:
            return {"ok": False, "error": "META_ACCESS_TOKEN or META_PAGE_ID missing"}

        # 1x1 transparent PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        try:
            resp = requests.post(
                f"https://graph.facebook.com/v21.0/{page_id}/photos",
                data={
                    "access_token": token,
                    "published": "false",
                    "temporary": "true",
                },
                files={"source": ("probe.png", png, "image/png")},
                timeout=60,
            )
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

        if resp.status_code == 200:
            return {"ok": True, "photo_id": resp.json().get("id")}

        err = resp.json().get("error", {})
        return {
            "ok": False,
            "error": err.get("message", resp.text),
            "code": err.get("code"),
            "subcode": err.get("error_subcode"),
        }

    @staticmethod
    def verify_connection(config: AppConfig) -> dict:
        """Test Meta API credentials and return account info."""
        token = (config.meta_access_token or "").strip()
        ig_id = (config.meta_ig_user_id or "").strip()
        if not token or not ig_id:
            return {"ok": False, "error": "META_ACCESS_TOKEN or META_IG_USER_ID missing"}
        if not token.startswith("EAA"):
            return {
                "ok": False,
                "error": "META_ACCESS_TOKEN must start with EAA (Facebook Graph API token)",
            }

        resp = requests.get(
            f"https://graph.facebook.com/v21.0/{ig_id}",
            params={
                "access_token": token,
                "fields": "id,username,name,profile_picture_url",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": resp.json().get("error", {}).get("message", resp.text)}

        token_info = MetaScheduler.inspect_token(
            token, config.meta_app_id, config.meta_app_secret
        )
        photo_probe = MetaScheduler.probe_photo_upload(config)
        missing = []
        if token_info.get("ok"):
            scopes = set(token_info.get("scopes", []))
            missing = [p for p in MetaScheduler.PHOTO_PERMISSIONS if p not in scopes]

        return {
            "ok": True,
            "account": resp.json(),
            "token_info": token_info,
            "photo_probe": photo_probe,
            "missing_photo_permissions": missing,
        }

    @staticmethod
    def discover_accounts(token: str) -> dict:
        """List Facebook Pages + linked Instagram IDs for a Graph API user token."""
        token = (token or "").strip()
        if not token:
            return {"ok": False, "error": "No token provided"}
        if token.startswith("IGA"):
            return {
                "ok": False,
                "error": (
                    "This looks like an Instagram Login token (IGA...). "
                    "Rahasya needs a Facebook Graph API token (EAA...) from Graph API Explorer."
                ),
            }
        if not token.startswith("EAA") and not token.startswith("EAAG"):
            return {
                "ok": False,
                "error": "Token must be a Facebook Graph API token (usually starts with EAA...)",
            }

        me = requests.get(
            "https://graph.facebook.com/v21.0/me",
            params={"access_token": token, "fields": "id,name"},
            timeout=30,
        )
        if me.status_code != 200:
            err = me.json().get("error", {})
            return {"ok": False, "error": err.get("message", me.text)}

        pages: list[dict] = []
        url = "https://graph.facebook.com/v21.0/me/accounts"
        params = {
            "access_token": token,
            "fields": "id,name,access_token,instagram_business_account{id,username,name}",
            "limit": "100",
        }
        while url:
            resp = requests.get(url, params=params if "me/accounts" in url else None, timeout=30)
            if resp.status_code != 200:
                err = resp.json().get("error", {})
                return {"ok": False, "error": err.get("message", resp.text)}
            body = resp.json()
            pages.extend(body.get("data", []))
            next_url = body.get("paging", {}).get("next")
            url = next_url or ""
            params = {}

        return {
            "ok": True,
            "user": me.json(),
            "pages": pages,
        }

    @staticmethod
    def fetch_page_token(user_token: str, page_id: str) -> dict:
        """Get Page access token when /me/accounts is empty but PAGE_ID is known."""
        user_token = (user_token or "").strip()
        page_id = (page_id or "").strip()
        if not user_token or not page_id:
            return {"ok": False, "error": "Need user token and page id"}

        resp = requests.get(
            f"https://graph.facebook.com/v21.0/{page_id}",
            params={"access_token": user_token, "fields": "id,name,access_token"},
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return {"ok": False, "error": err.get("message", resp.text)}

        data = resp.json()
        page_token = data.get("access_token", "")
        if not page_token:
            return {
                "ok": False,
                "error": (
                    "No page token returned — your Facebook user may not be Admin on this Page. "
                    "Add yourself as Page Admin or create a new Page with this Facebook account."
                ),
            }
        return {"ok": True, "page": data, "page_token": page_token}
