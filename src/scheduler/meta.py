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
            reel_path, reel_caption, cover_url=cover_url, publish_at=reel_time
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
        params: dict[str, str] = {
            "access_token": self.access_token,
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:2200],
            "share_to_feed": "true",
        }
        if cover_url:
            params["cover_url"] = cover_url
        # Do not pass publish_at here — Instagram rejects it on /media container create.

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media",
            params=params,
            timeout=60,
        )
        if resp.status_code >= 400:
            self._log_api_error("reel container", resp)
        resp.raise_for_status()
        data = resp.json()
        container_id = data["id"]
        self.logger.info(f"Reel container created: {container_id}")

        self._resumable_upload(container_id, video_path)
        return container_id

    def _resumable_upload(self, container_id: str, file_path: Path) -> None:
        file_size = file_path.stat().st_size
        headers = {
            **self._headers(),
            "offset": "0",
            "file_size": str(file_size),
        }
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{self.RUPLOAD_URL}/{container_id}",
                headers=headers,
                data=f,
                timeout=600,
            )
        resp.raise_for_status()
        self.logger.info(f"Uploaded {file_path.name} ({file_size} bytes)")

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
        if publish_at:
            params["publish_at"] = str(self._unix_publish_at(publish_at))

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
            resp.raise_for_status()
            photo_id = resp.json().get("id")
            if not photo_id:
                return None
            url_resp = requests.get(
                f"{self.GRAPH_URL}/{photo_id}",
                params={"access_token": self.access_token, "fields": "images"},
                timeout=30,
            )
            url_resp.raise_for_status()
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
    def verify_connection(config: AppConfig) -> dict:
        """Test Meta API credentials and return account info."""
        token = (config.meta_access_token or "").strip()
        ig_id = (config.meta_ig_user_id or "").strip()
        if not token or not ig_id:
            return {"ok": False, "error": "META_ACCESS_TOKEN or META_IG_USER_ID missing"}
        if not token.startswith("EAA"):
            return {
                "ok": False,
                "error": "META_ACCESS_TOKEN must start with EAA (Facebook Graph API user token)",
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
        return {"ok": True, "account": resp.json()}
