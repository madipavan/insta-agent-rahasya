"""Generate episode outlines for a novel using CrewAI master arc."""

from __future__ import annotations

from src.agents.crews.planner_crew import PlannerCrew
from src.book_queue.models import Novel
from src.book_queue.pacing import chapter_ranges, estimate_episode_count
from src.book_queue.store import Database
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.provider import get_provider


class EpisodePlanner:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.db = Database(config.path("db_path"))
        self.planner_crew = PlannerCrew(config, logger)

    def create_outline(self, novel: Novel) -> None:
        if self.db.episode_count_for_novel(novel.id) > 0:
            return

        episode_count = novel.estimated_episodes or estimate_episode_count(novel.chapter_count)
        ranges = chapter_ranges(novel.chapter_count, episode_count)

        self.logger.start("episode_planner", f"{novel.title} — {episode_count} episodes (crewai)")

        arc_result = self._generate_master_arc(novel, episode_count, ranges)
        if isinstance(arc_result, dict):
            episodes_data = arc_result.get("episodes", [])
            self.db.set_novel_story_bible(
                novel.id,
                novel_logline=arc_result.get("novel_logline", ""),
                story_summary=arc_result.get("story_summary", ""),
                retention_strategy=arc_result.get("retention_strategy", ""),
            )
        else:
            episodes_data = arc_result

        for i, (start, end) in enumerate(ranges, start=1):
            ep_data = episodes_data[i - 1] if i - 1 < len(episodes_data) else {}
            beat = ep_data.get("plot_beat_summary", f"Episode {i}: chapters {start}-{end}.")
            cumulative = ep_data.get("cumulative_synopsis", beat)
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
            )

        self.logger.ok("episode_planner", f"created {episode_count} episode-ready briefs")

    def _generate_master_arc(
        self,
        novel: Novel,
        episode_count: int,
        ranges: list[tuple[int, int]],
    ) -> dict:
        try:
            return self.planner_crew.create_master_arc(novel, episode_count, ranges)
        except Exception as exc:
            self.logger.warn("episode_planner", f"CrewAI arc failed: {exc} — fallback sequential")
            episodes = self._fallback_sequential(novel, episode_count, ranges)
            return {"episodes": episodes, "novel_logline": "", "story_summary": "", "retention_strategy": ""}

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
                "Original paraphrase only. Binge-worthy hooks."
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
