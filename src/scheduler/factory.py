"""Post scheduler factory — Meta or Metricool."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.scheduler.meta import MetaScheduler
from src.scheduler.metricool import MetricoolScheduler
from src.script_gen.post_details import PostDetails


class PostScheduler(Protocol):
    def queue_posts(
        self,
        reel_path: Path,
        static_paths: list[Path] | Path,
        caption: str,
        bundle_id: str,
        *,
        thumbnail_path: Path | None = None,
        post_details: PostDetails | None = None,
    ) -> str: ...


def get_scheduler(config: AppConfig, logger: PipelineLogger) -> PostScheduler:
    provider = (config.post_provider or "meta").lower()
    if provider == "metricool":
        return _MetricoolAdapter(MetricoolScheduler(config, logger))
    return _MetaAdapter(MetaScheduler(config, logger))


class _MetaAdapter:
    def __init__(self, scheduler: MetaScheduler) -> None:
        self._scheduler = scheduler

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
        return self._scheduler.queue_posts(
            reel_path,
            static_paths,
            caption,
            bundle_id,
            thumbnail_path=thumbnail_path,
            post_details=post_details,
        )


class _MetricoolAdapter:
    def __init__(self, scheduler: MetricoolScheduler) -> None:
        self._scheduler = scheduler

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
        cap = post_details.reel_caption if post_details else caption
        return self._scheduler.queue_posts(reel_path, static_paths, cap, bundle_id)
