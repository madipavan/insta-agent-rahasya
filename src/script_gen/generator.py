"""Script generation via LangGraph + CrewAI."""

from __future__ import annotations

from pathlib import Path

from src.agents.graphs.script_graph import ScriptGraphRunner
from src.book_queue.models import EpisodeContext, ScriptOutput
from src.book_queue.store import Database
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger


class ScriptGenerator:
    def __init__(self, config: AppConfig, logger: PipelineLogger, db: Database | None = None) -> None:
        self.config = config
        self.logger = logger
        self.db = db or Database(config.path("db_path"))
        self.runner = ScriptGraphRunner(config, logger)

    def generate(self, context: EpisodeContext) -> ScriptOutput:
        self.logger.start("script_gen", f"ep {context.episode.episode_num} (langgraph+crewai)")
        samples = self._load_sample_scripts()
        previous = self.db.get_previous_episode_context(
            context.novel.id,
            context.episode.episode_num,
        )
        script = self.runner.generate(context, samples, previous)
        spoken = script.episode_script()
        if not spoken:
            raise ValueError("Script generation returned empty voiceover_script")
        self.logger.ok("script_gen", f"{len(spoken)} chars")
        return script

    def _load_sample_scripts(self) -> list[str]:
        scripts_dir = self.config.path("sample_scripts")
        if not scripts_dir.exists():
            return []
        for path in sorted(scripts_dir.glob("*.txt")):
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return [text[:700]]
        return []

    def format_caption(self, context: EpisodeContext, script: ScriptOutput) -> str:
        template = self.config.caption_template or (
            "{caption_hook}\n\n{caption_teaser}\n\n"
            "Part {episode}/{total} of \"{novel_title}\"\n{cta}\n\n{hashtags}"
        )
        return template.format(
            caption_hook=script.caption_hook,
            caption_teaser=script.caption_teaser,
            episode=context.episode.episode_num,
            total=context.total_episodes,
            novel_title=context.novel.title,
            cta=self.config.cta,
            hashtags=self.config.hashtags,
        )
