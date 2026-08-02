"""Novel queue orchestration."""

from __future__ import annotations

from pathlib import Path

from src.book_queue.discovery import NovelDiscovery
from src.book_queue.models import EpisodeContext, Novel
from src.book_queue.store import Database
from src.config import AppConfig
from src.episode_planner.planner import EpisodePlanner
from src.pipeline.logger import PipelineLogger


class BookQueue:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.db = Database(config.path("db_path"))
        self.planner = EpisodePlanner(config, logger)
        self.discovery = NovelDiscovery(config, self.db, logger)

    def ensure_queue(self) -> None:
        seed_path = self.config.path("novels_seed")
        if self.db.count_queued_novels() == 0 and not self.db.get_active_novel():
            imported = self.db.import_seed_file(seed_path)
            if imported:
                self.logger.info(f"Imported {imported} novels from seed file")

        if self.db.count_queued_novels() < self.config.discovery.min_queue_size:
            self.discovery.run()

    def activate_next_novel(self) -> Novel:
        active = self.db.get_active_novel()
        if active:
            return active

        next_novel = self.db.get_next_queued_novel()
        if not next_novel:
            self.ensure_queue()
            next_novel = self.db.get_next_queued_novel()
        if not next_novel:
            raise RuntimeError("No novels available in queue after discovery")

        self.db.set_novel_status(next_novel.id, "active")
        self.planner.create_outline(next_novel)
        activated = self.db.get_novel(next_novel.id)
        if not activated:
            raise RuntimeError("Failed to activate novel")
        self.logger.info(f"Activated novel: {activated.title} by {activated.author}")
        return activated

    def get_today_context(self) -> EpisodeContext:
        self.ensure_queue()
        novel = self.db.get_active_novel()
        if not novel:
            novel = self.activate_next_novel()

        episode = self.db.get_next_pending_episode(novel.id)
        if not episode:
            self.complete_novel(novel)
            novel = self.activate_next_novel()
            episode = self.db.get_next_pending_episode(novel.id)
            if not episode:
                raise RuntimeError("No pending episodes for active novel")

        return EpisodeContext(
            novel=novel,
            episode=episode,
            total_episodes=novel.estimated_episodes,
        )

    def complete_novel(self, novel: Novel) -> None:
        self.db.set_novel_status(novel.id, "completed")
        self.logger.info(f"Completed novel: {novel.title}")

    def mark_episode_generated(self, context: EpisodeContext) -> None:
        self.db.set_episode_status(context.episode.id, "generated")
        self.db.increment_episode(context.novel.id)

        if context.episode.episode_num >= context.total_episodes:
            self.complete_novel(context.novel)

    def status_summary(self) -> dict:
        active = self.db.get_active_novel()
        queued = self.db.list_novels("queued")
        completed = self.db.list_novels("completed")
        pending_reviews = self.db.list_pending_reviews()
        return {
            "active": active,
            "queued_count": len(queued),
            "completed_count": len(completed),
            "pending_reviews": len(pending_reviews),
            "queued": queued,
        }
