"""CrewAI-style episode arc planning via LangChain."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.llm_factory import get_chat_model
from src.book_queue.models import Novel
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.craft_rules import SCRIPT_CRAFT_RULES
from src.utils.json_parse import parse_llm_json
from src.utils.llm_text import extract_llm_text

STRATEGIST_SYSTEM = f"""You are a Story Arc Strategist for Instagram suspense reels.
Design binge-worthy episodic arcs with genuine storytelling — not vague summaries.
Each episode must name characters, places, and specific plot events.
Episodes chain like a TV series but NEVER recap the previous episode in the next beat.
Every episode must cover UNIQUE new events — no repeated plots.
planned_hook must be danger, shock, or a direct question — NEVER pure scene-setting or backstory.
Original paraphrase only — never quote the book. Output valid JSON only.

{SCRIPT_CRAFT_RULES}"""

BEAT_WRITER_SYSTEM = f"""You are an Episode Beat Writer. Refine arc JSON for scriptwriters.
First create a tight novel-level story bible (logline + full-story summary in 6-8 sentences).
Then ensure each episode has: plot_beat_summary (specific events, names, stakes),
cumulative_synopsis (max 3 sentences, position only — not a spoken recap),
planned_hook, planned_cliffhanger, retention_angle.
planned_hook = danger/shock/question only (no "एक दिन…" / time-place setup).
Episodes must feel connected WITHOUT explaining last episode.
All plot beats must be distinct. Output valid JSON only.

{SCRIPT_CRAFT_RULES}"""


class PlannerCrew:
    """Arc Strategist + Beat Writer crew for episode-ready novel outlines."""

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.strategist_llm = get_chat_model(config, temperature=0.6, logger=logger)
        self.beat_llm = get_chat_model(config, temperature=0.5, logger=logger)

    def create_master_arc(
        self,
        novel: Novel,
        episode_count: int,
        chapter_ranges: list[tuple[int, int]],
    ) -> dict[str, Any]:
        ranges_text = "\n".join(
            f"Ep {i}: chapters {s}-{e}" for i, (s, e) in enumerate(chapter_ranges, 1)
        )

        arc_prompt = (
            f"Series: {novel.title} by {novel.author} ({novel.country})\n"
            f"Total episodes: {episode_count}\n"
            f"Episode mapping:\n{ranges_text}\n"
        )
        if novel.novel_logline or novel.story_summary:
            arc_prompt += (
                f"\nExisting story bible (expand, do not discard):\n"
                f"Logline: {novel.novel_logline}\n"
                f"Summary: {novel.story_summary}\n"
                f"Retention: {novel.retention_strategy}\n"
            )
        arc_prompt += (
            "\nReturn JSON with keys: novel_logline, story_summary, retention_strategy, episodes (array).\n"
            "novel_logline: 1 punchy Hindi-friendly hook sentence for the whole series.\n"
            "story_summary: 6-8 sentences — full series arc (setup, stakes, twists, ending tease). "
            "Original Indian dark serial. Name the protagonist and central secret.\n"
            "Each episode object: episode_num, plot_beat_summary, cumulative_synopsis,\n"
            "planned_hook, planned_cliffhanger, retention_angle.\n"
            "plot_beat_summary must include character names and specific events — not generic 'tension rises'.\n"
            "Episodes must chain for binge UX without repeating plots or recapping prior episodes."
        )

        self.logger.info("planner_crew | arc strategist agent")
        arc_resp = self.strategist_llm.invoke([
            SystemMessage(content=STRATEGIST_SYSTEM),
            HumanMessage(content=arc_prompt),
        ])
        arc_data = parse_llm_json(extract_llm_text(arc_resp))

        refine_prompt = (
            "Review and finalize this master arc JSON. "
            "Ensure story_summary covers the FULL novel in 6-8 sentences. "
            "Ensure every episode has distinct hook + cliffhanger with named characters and events. "
            "Tighten cumulative_synopsis to max 4 sentences each.\n\n"
            f"{json.dumps(arc_data, ensure_ascii=False)}"
        )
        self.logger.info("planner_crew | beat writer agent")
        beat_resp = self.beat_llm.invoke([
            SystemMessage(content=BEAT_WRITER_SYSTEM),
            HumanMessage(content=refine_prompt),
        ])
        beat_text = extract_llm_text(beat_resp)
        if beat_text:
            try:
                final = parse_llm_json(beat_text)
            except json.JSONDecodeError:
                self.logger.warn("planner_crew", "beat writer JSON invalid — using strategist draft")
                final = arc_data
        else:
            self.logger.warn("planner_crew", "beat writer empty — using strategist draft")
            final = arc_data

        episodes = final.get("episodes", arc_data.get("episodes", []))
        if len(episodes) < episode_count:
            self.logger.warn(
                "planner_crew",
                f"arc returned {len(episodes)} episodes, expected {episode_count}",
            )
        return {
            "novel_logline": final.get("novel_logline", arc_data.get("novel_logline", "")),
            "story_summary": final.get("story_summary", arc_data.get("story_summary", "")),
            "retention_strategy": final.get(
                "retention_strategy", arc_data.get("retention_strategy", "")
            ),
            "episodes": episodes[:episode_count],
        }
