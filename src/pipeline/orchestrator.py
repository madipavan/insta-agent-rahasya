"""Main pipeline orchestrator."""

from __future__ import annotations

from pathlib import Path

from src.book_queue.queue import BookQueue
from src.book_queue.store import Database
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.review.bundle import ReviewBundleWriter
from src.script_gen.export import write_script_txt, write_transcript_txt
from src.script_gen.post_details import build_post_details, write_post_details_json, write_post_details_txt
from src.review.telegram import TelegramNotifier


class Pipeline:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = PipelineLogger(config.path("logs_dir"))
        self.db = Database(config.path("db_path"))
        self._queue: BookQueue | None = None
        self.review = ReviewBundleWriter(config, self.db)
        self.telegram = TelegramNotifier(config, self.logger)
        self._script_gen = None
        self._voiceover = None
        self._stock = None
        self._reel = None
        self._static_post = None
        self._novel_assets = None
        self._hashtags = None

    @property
    def queue(self) -> BookQueue:
        if self._queue is None:
            self._queue = BookQueue(self.config, self.logger)
        return self._queue

    @property
    def script_gen(self):
        if self._script_gen is None:
            from src.script_gen.generator import ScriptGenerator

            self._script_gen = ScriptGenerator(self.config, self.logger, self.db)
        return self._script_gen

    @property
    def voiceover(self):
        if self._voiceover is None:
            from src.voiceover.provider import get_voiceover_provider

            self._voiceover = get_voiceover_provider(self.config, self.logger)
        return self._voiceover

    @property
    def stock(self):
        if self._stock is None:
            from src.visuals.stock import StockResolver

            self._stock = StockResolver(self.config, self.logger)
        return self._stock

    @property
    def reel(self):
        if self._reel is None:
            from src.visuals.assembler import ReelAssembler

            self._reel = ReelAssembler(self.config, self.logger)
        return self._reel

    @property
    def static_post(self):
        if self._static_post is None:
            from src.static_post.generator import StaticPostGenerator

            self._static_post = StaticPostGenerator(self.config, self.logger)
        return self._static_post

    @property
    def novel_assets(self):
        if self._novel_assets is None:
            from src.novel_assets import NovelAssetManager

            self._novel_assets = NovelAssetManager(
                self.config, self.logger, self.db, stock=self.stock
            )
        return self._novel_assets

    @property
    def hashtags(self):
        if self._hashtags is None:
            from src.hashtags.fetcher import HashtagFetcher

            self._hashtags = HashtagFetcher(self.config, self.logger)
        return self._hashtags

    def run(self) -> str:
        self.logger.start("pipeline", "daily run")
        try:
            context = self.queue.get_today_context()
            script = self.script_gen.generate(context)
            caption = self.script_gen.format_caption(context, script)

            work_dir = self.config.path("output_dir") / "work" / self.review.create_bundle_id(context)
            work_dir.mkdir(parents=True, exist_ok=True)

            spoken_text = script.episode_script()
            voiceover_path = self.voiceover.generate(
                spoken_text,
                work_dir / "voiceover.mp3",
            )

            transcript_path = write_transcript_txt(
                spoken_text,
                work_dir / "transcript.txt",
            )

            assets = self.novel_assets.ensure(context.novel, script.stock_keywords)
            hook_for_thumb = ""
            if script.on_screen_text:
                hook_for_thumb = script.on_screen_text[0]
            elif script.hook:
                hook_for_thumb = script.hook
            thumbnail_path = self.novel_assets.episode_thumbnail(
                context.novel,
                context.episode.episode_num,
                context.total_episodes,
                work_dir / "thumbnail.png",
                assets=assets,
                hook_text=hook_for_thumb,
            )

            stock_paths = self.stock.resolve_visuals(script.stock_keywords, work_dir)
            reel_path = self.reel.assemble(
                context,
                script,
                voiceover_path,
                stock_paths,
                work_dir / "reel.mp4",
                bgm_path=assets.bgm_path,
            )
            static_paths = self.static_post.generate_all(
                context, script, work_dir, stock_paths
            )

            script_txt_path = write_script_txt(
                context, script, work_dir / "script.txt", caption=caption
            )

            ranked_hashtags = self.hashtags.build(
                context, extra_keywords=script.stock_keywords
            )
            post_details = build_post_details(
                context,
                script,
                self.config,
                caption,
                static_slide_count=len(static_paths),
                hashtags=ranked_hashtags,
            )
            post_details_txt_path = write_post_details_txt(
                post_details, work_dir / "post_details.txt"
            )
            post_details_json_path = write_post_details_json(
                post_details, work_dir / "post_details.json"
            )

            bundle_id, bundle_dir = self.review.write(
                context,
                script,
                caption,
                voiceover_path,
                reel_path,
                static_paths,
                thumbnail_path=thumbnail_path,
                script_txt_path=script_txt_path,
                transcript_path=transcript_path,
                post_details_txt_path=post_details_txt_path,
                post_details_json_path=post_details_json_path,
            )

            self.queue.mark_episode_generated(context)
            self.db.log_post(
                context.novel.id,
                context.episode.episode_num,
                bundle_id,
                "generated",
            )

            if self.config.review_required:
                self.telegram.send_review_notification(
                    bundle_id,
                    caption,
                    script.episode_script(),
                    bundle_dir,
                )
                self.logger.ok("pipeline", f"awaiting review: {bundle_id}")
            elif self.config.auto_publish:
                self.approve_and_post(bundle_id)
            else:
                self.db.set_review_status(bundle_id, "pending_publish")
                self.logger.ok(
                    "pipeline",
                    f"generated — queued for publish at {self.config.post_time} "
                    f"(run: python main.py publish): {bundle_id}",
                )

            return bundle_id
        except Exception as exc:
            self.logger.fail("pipeline", str(exc))
            self.telegram.send_error(str(exc))
            raise

    def approve_and_post(self, bundle_id: str) -> None:
        from src.pipeline.publisher import approve_and_post

        approve_and_post(self.config, bundle_id, logger=self.logger)

    def reject_bundle(self, bundle_id: str, reason: str = "") -> None:
        self.review.reject(bundle_id, reason)
        bundle = self.db.get_review_bundle(bundle_id)
        if bundle:
            self.db.log_post(
                bundle["novel_id"],
                bundle["episode_num"],
                bundle_id,
                "rejected",
                error=reason,
            )
        self.telegram.send_info(f"❌ Rejected: `{bundle_id}` — {reason}")

    def publish_pending(self) -> str | None:
        from src.pipeline.publisher import publish_pending

        return publish_pending(self.config, logger=self.logger)
