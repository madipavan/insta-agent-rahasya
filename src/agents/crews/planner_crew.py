"""CrewAI-style episode arc planning via LangChain."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.llm_factory import get_chat_model
from src.book_queue.models import Novel
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.json_parse import parse_llm_json

STRATEGIST_SYSTEM = """You are a Story Arc Strategist for Instagram suspense reels.
Design binge-worthy episodic arcs. Each episode hooks in 3 seconds and ends on a cliffhanger.
Original paraphrase only — never quote the book. Output valid JSON only."""

BEAT_WRITER_SYSTEM = """You are an Episode Beat Writer. Refine arc JSON for scriptwriters.
Each episode needs: plot_beat_summary, cumulative_synopsis (max 4 sentences),
planned_hook, planned_cliffhanger, retention_angle. Output valid JSON only."""


class PlannerCrew:
    """Arc Strategist + Beat Writer crew for episode-ready novel outlines."""

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.strategist_llm = get_chat_model(config, temperature=0.6)
        self.beat_llm = get_chat_model(config, temperature=0.5)

    def create_master_arc(
        self,
        novel: Novel,
        episode_count: int,
        chapter_ranges: list[tuple[int, int]],
    ) -> list[dict[str, Any]]:
        ranges_text = "\n".join(
            f"Ep {i}: chapters {s}-{e}" for i, (s, e) in enumerate(chapter_ranges, 1)
        )

        arc_prompt = (
            f"Novel: {novel.title} by {novel.author} ({novel.country})\n"
            f"Total episodes: {episode_count}\n"
            f"Chapter mapping:\n{ranges_text}\n\n"
            "Return JSON with keys: novel_logline, retention_strategy, episodes (array).\n"
            "Each episode object: episode_num, plot_beat_summary, cumulative_synopsis,\n"
            "planned_hook, planned_cliffhanger, retention_angle.\n"
            "Episodes must chain seamlessly for binge UX."
        )

        self.logger.info("planner_crew | arc strategist agent")
        arc_resp = self.strategist_llm.invoke([
            SystemMessage(content=STRATEGIST_SYSTEM),
            HumanMessage(content=arc_prompt),
        ])
        arc_data = parse_llm_json(str(arc_resp.content))

        refine_prompt = (
            "Review and finalize this master arc JSON. "
            "Ensure every episode has distinct hook + cliffhanger. "
            "Tighten cumulative_synopsis to max 4 sentences each.\n\n"
            f"{json.dumps(arc_data, ensure_ascii=False)}"
        )
        self.logger.info("planner_crew | beat writer agent")
        beat_resp = self.beat_llm.invoke([
            SystemMessage(content=BEAT_WRITER_SYSTEM),
            HumanMessage(content=refine_prompt),
        ])
        final = parse_llm_json(str(beat_resp.content))

        episodes = final.get("episodes", arc_data.get("episodes", []))
        if len(episodes) < episode_count:
            self.logger.warn(
                "planner_crew",
                f"arc returned {len(episodes)} episodes, expected {episode_count}",
            )
        return episodes[:episode_count]
