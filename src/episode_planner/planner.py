"""Generate episode outlines + upfront Hindi scripts from novel PDF."""

from __future__ import annotations

import json

from src.agents.crews.novel_script_batch_crew import NovelScriptBatchCrew
from src.agents.crews.planner_crew import PlannerCrew
from src.book_queue.models import Novel
from src.book_queue.pacing import chapter_ranges, estimate_episode_count
from src.book_queue.store import Database
from src.config import AppConfig
from src.novel_assets.pdf_source import NovelPdfSource
from src.pipeline.logger import PipelineLogger
from src.script_gen.provider import get_provider


class EpisodePlanner:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.db = Database(config.path("db_path"))
        self.planner_crew = PlannerCrew(config, logger)
        self.batch_crew = NovelScriptBatchCrew(config, logger)
        self.pdf_source = NovelPdfSource(config, logger)

    def create_outline(self, novel: Novel) -> None:
        if self.db.episode_count_for_novel(novel.id) > 0:
            return

        max_eps = getattr(self.config, "max_episodes", 12)
        episode_count = novel.estimated_episodes or estimate_episode_count(
            novel.chapter_count, max_episodes=max_eps
        )
        episode_count = min(episode_count, max_eps)
        if novel.estimated_episodes != episode_count:
            self.db.set_estimated_episodes(novel.id, episode_count)
        ranges = chapter_ranges(novel.chapter_count, episode_count)

        self.logger.start(
            "episode_planner",
            f"{novel.title} — {episode_count} episodes (pdf→batch scripts)",
        )

        package = self._build_from_pdf(novel, episode_count, ranges)
        if package is None:
            self.logger.warn(
                "episode_planner",
                "PDF batch path failed — falling back to title/author arc (no scripts)",
            )
            package = self._generate_master_arc(novel, episode_count, ranges)

        episodes_data = package.get("episodes", [])
        self.db.set_novel_story_bible(
            novel.id,
            novel_logline=package.get("novel_logline", ""),
            story_summary=package.get("story_summary", ""),
            retention_strategy=package.get("retention_strategy", ""),
        )

        for i, (start, end) in enumerate(ranges, start=1):
            ep_data = episodes_data[i - 1] if i - 1 < len(episodes_data) else {}
            if not isinstance(ep_data, dict):
                ep_data = {}
            beat = ep_data.get("plot_beat_summary", f"Episode {i}: chapters {start}-{end}.")
            cumulative = ep_data.get("cumulative_synopsis", beat)
            script_obj = ep_data.get("script")
            script_json = ""
            if isinstance(script_obj, dict) and (
                script_obj.get("voiceover_script") or script_obj.get("episode_only_script")
            ):
                script_json = json.dumps(script_obj, ensure_ascii=False)
            elif isinstance(ep_data.get("voiceover_script"), str):
                script_json = json.dumps(ep_data, ensure_ascii=False)

            self.db.add_episode(
                novel_id=novel.id,
                episode_num=i,
                chapter_start=start,
                chapter_end=end,
                plot_beat_summary=beat,
                cumulative_synopsis=cumulative,
                status="pending",
                planned_hook=ep_data.get("planned_hook", ""),
                planned_cliffhanger=ep_data.get("planned_cliffhanger", ""),
                retention_angle=ep_data.get("retention_angle", ""),
                script_json=script_json,
            )

        saved = sum(
            1
            for i in range(1, episode_count + 1)
            if self.db.get_episode_script_json(novel.id, i)
        )
        self.logger.ok(
            "episode_planner",
            f"created {episode_count} episodes ({saved} with saved scripts)",
        )

    def _build_from_pdf(
        self,
        novel: Novel,
        episode_count: int,
        ranges: list[tuple[int, int]],
    ) -> dict | None:
        try:
            pdf_path = self.pdf_source.ensure_pdf(
                novel.id, novel.title, novel.source_link
            )
            self.db.set_novel_pdf_path(novel.id, str(pdf_path))
            self.logger.info(f"episode_planner | sending PDF to LLM: {pdf_path}")
            return self.batch_crew.build_full_package(
                novel, pdf_path, episode_count, ranges
            )
        except Exception as exc:
            self.logger.warn("episode_planner", f"PDF/batch pipeline failed: {exc}")
            return None

    def _generate_master_arc(
        self,
        novel: Novel,
        episode_count: int,
        ranges: list[tuple[int, int]],
    ) -> dict:
        try:
            return self.planner_crew.create_master_arc(novel, episode_count, ranges)
        except Exception as exc:
            self.logger.warn(
                "episode_planner", f"CrewAI arc failed: {exc} — fallback sequential"
            )
            episodes = self._fallback_sequential(novel, episode_count, ranges)
            return {
                "episodes": episodes,
                "novel_logline": "",
                "story_summary": "",
                "retention_strategy": "",
            }

    def _fallback_sequential(
        self,
        novel: Novel,
        episode_count: int,
        ranges: list[tuple[int, int]],
    ) -> list[dict]:
        provider = get_provider(self.config)
        cumulative = ""
        episodes: list[dict] = []

        for i, (start, end) in enumerate(ranges, start=1):
            prompt = (
                f"Novel: {novel.title} by {novel.author}\n"
                f"Episode {i}/{episode_count}, chapters {start}-{end}.\n"
                f"Story so far: {cumulative or 'Beginning.'}\n"
                "Return JSON: plot_beat_summary, cumulative_synopsis (max 4 sentences), "
                "planned_hook, planned_cliffhanger, retention_angle. "
                "Original paraphrase only. Binge-worthy hooks. "
                "Do NOT recap the previous episode. NEW events only."
            )
            try:
                data = provider.complete_json(prompt)
            except Exception:
                data = {
                    "plot_beat_summary": f"Episode {i} tension rises.",
                    "cumulative_synopsis": cumulative,
                    "planned_hook": "",
                    "planned_cliffhanger": "",
                    "retention_angle": "",
                }
            cumulative = data.get("cumulative_synopsis", cumulative)
            data["episode_num"] = i
            episodes.append(data)

        return episodes
