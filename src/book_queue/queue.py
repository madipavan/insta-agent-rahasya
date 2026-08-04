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
        self._planner: EpisodePlanner | None = None
        self._discovery: NovelDiscovery | None = None

    @property
    def planner(self) -> EpisodePlanner:
        if self._planner is None:
            self._planner = EpisodePlanner(self.config, self.logger)
        return self._planner

    @property
    def discovery(self) -> NovelDiscovery:
        if self._discovery is None:
            self._discovery = NovelDiscovery(self.config, self.db, self.logger)
        return self._discovery

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

        output_dir = self.config.path("output_dir")
        self.db.log_episode_state(novel.id, self.logger)

        for _ in range(novel.estimated_episodes + 2):
            synced = self.db.sync_episode_progress(novel.id, output_dir)
            if synced:
                self.logger.info(
                    f"queue | synced {synced} completed episode(s) from bundles/output"
                )

            episode = self.db.get_next_pending_episode(novel.id)
            if not episode:
                self.complete_novel(novel)
                novel = self.activate_next_novel()
                self.db.log_episode_state(novel.id, self.logger)
                episode = self.db.get_next_pending_episode(novel.id)
                if not episode:
                    raise RuntimeError("No pending episodes for active novel")

            if self.db.episode_output_exists(novel, episode.episode_num, output_dir):
                marked = self.db.set_episode_status_by_num(
                    novel.id, episode.episode_num, "generated"
                )
                self.db.refresh_novel_current_episode(novel.id)
                self.logger.info(
                    f"queue | ep {episode.episode_num} already has reel.mp4 on disk "
                    f"{'(marked generated)' if marked else '(already generated)'} — skipping"
                )
                continue

            self.logger.info(
                f"queue | generating {novel.title} ep {episode.episode_num}/"
                f"{novel.estimated_episodes}"
            )
            return EpisodeContext(
                novel=novel,
                episode=episode,
                total_episodes=novel.estimated_episodes,
            )

        raise RuntimeError("Could not find a pending episode to generate")

    def complete_novel(self, novel: Novel) -> None:
        self.db.set_novel_status(novel.id, "completed")
        self.logger.info(f"Completed novel: {novel.title}")

    def skip_to_next_novel(self, clean_output: bool = True) -> Novel:
        """Abandon current novel, wipe its pipeline data, activate next in queue."""
        active = self.db.get_active_novel()
        if not active:
            raise RuntimeError("No active novel to skip")

        self.logger.info(f"Skipping novel: {active.title} (id={active.id})")
        self.db.set_novel_status(active.id, "abandoned")
        self.db.delete_novel_data(active.id)

        if clean_output:
            self._clean_novel_output(active)

        self.ensure_queue()
        next_novel = self.db.get_next_queued_novel()
        if not next_novel:
            raise RuntimeError("No novels left in queue after skip")

        self.db.set_novel_status(next_novel.id, "active")
        self.planner.create_outline(next_novel)
        activated = self.db.get_novel(next_novel.id)
        if not activated:
            raise RuntimeError("Failed to activate next novel")
        self.logger.info(f"Activated next novel: {activated.title} by {activated.author}")
        return activated

    def _clean_novel_output(self, novel: Novel) -> None:
        """Remove generated output folders for a novel (no Instagram analytics needed)."""
        import shutil

        slug = novel.title.lower().replace(" ", "_").replace("'", "")
        slug = "".join(c for c in slug if c.isalnum() or c == "_")
        output_dir = self.config.path("output_dir")
        removed = 0
        for sub in ("review", "approved", "posted", "ready_to_upload", "work"):
            folder = output_dir / sub
            if not folder.exists():
                continue
            for child in folder.iterdir():
                if child.is_dir() and slug in child.name.lower():
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1
        if removed:
            self.logger.info(f"Cleaned {removed} output folders for {novel.title}")

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
