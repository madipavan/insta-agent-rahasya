"""Metricool scheduler integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger


class MetricoolScheduler:
    BASE_URL = "https://api.metricool.com/v1"

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger

    def queue_posts(
        self,
        reel_path: Path,
        static_paths: list[Path] | Path,
        caption: str,
        bundle_id: str,
    ) -> str:
        if isinstance(static_paths, Path):
            static_paths = [static_paths]

        self.logger.start("metricool", bundle_id)
        if not self.config.metricool_api_key or not self.config.metricool_user_id:
            self.logger.warn("metricool", "not configured — saving package for manual upload")
            return self._save_manual_package(reel_path, static_paths, caption, bundle_id)

        scheduled_time = self._next_post_time()
        reel_id = self._schedule_post(reel_path, caption, scheduled_time, media_type="video")
        static_ids: list[str] = []
        for i, static_path in enumerate(static_paths):
            sid = self._schedule_post(
                static_path,
                caption,
                scheduled_time + timedelta(minutes=5 + i * 2),
                media_type="image",
            )
            static_ids.append(sid)
        result_id = f"reel:{reel_id};static:{','.join(static_ids)}"
        self.logger.ok("metricool", result_id)
        return result_id

    def _next_post_time(self) -> datetime:
        tz = ZoneInfo(self.config.timezone)
        now = datetime.now(tz)
        hour, minute = map(int, self.config.post_time.split(":"))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)
        return scheduled

    def _schedule_post(
        self,
        media_path: Path,
        caption: str,
        scheduled_time: datetime,
        media_type: str,
    ) -> str:
        headers = {
            "X-Mc-Auth": self.config.metricool_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "userId": self.config.metricool_user_id,
            "text": caption,
            "scheduledDate": scheduled_time.isoformat(),
            "provider": "instagram",
            "mediaType": media_type,
            "mediaPath": str(media_path),
        }
        try:
            resp = requests.post(
                f"{self.BASE_URL}/schedule",
                headers=headers,
                json=payload,
                timeout=60,
            )
            if resp.status_code == 404 or resp.status_code == 405:
                return self._upload_media_fallback(media_path, caption, scheduled_time)
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("id", "queued"))
        except requests.RequestException as exc:
            self.logger.warn("metricool", f"schedule failed: {exc}")
            return self._upload_media_fallback(media_path, caption, scheduled_time)

    def _upload_media_fallback(
        self, media_path: Path, caption: str, scheduled_time: datetime
    ) -> str:
        self.logger.warn(
            "metricool",
            f"API schedule unavailable — manual upload needed for {media_path.name}",
        )
        return f"manual:{media_path.name}"

    def _save_manual_package(
        self,
        reel_path: Path,
        static_paths: list[Path],
        caption: str,
        bundle_id: str,
    ) -> str:
        package_dir = self.config.path("output_dir") / "ready_to_upload" / bundle_id
        package_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(reel_path, package_dir / "reel.mp4")
        for i, sp in enumerate(static_paths):
            shutil.copy2(sp, package_dir / f"static_post_{i + 1:02d}.png")
        if static_paths:
            shutil.copy2(static_paths[0], package_dir / "static_post.png")
        (package_dir / "caption.txt").write_text(caption, encoding="utf-8")
        (package_dir / "UPLOAD_INSTRUCTIONS.txt").write_text(
            f"Upload reel.mp4 as Instagram Reel.\n"
            f"Upload all static_post_*.png as a CAROUSEL post ({len(static_paths)} slides).\n"
            f"Scheduled time: {self.config.post_time} {self.config.timezone}\n",
            encoding="utf-8",
        )
        return f"manual_package:{bundle_id}"
