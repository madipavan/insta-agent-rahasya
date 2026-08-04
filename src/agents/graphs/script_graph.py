"""LangGraph script generation with validation loop."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.crews.script_crew import ScriptCrew
from src.book_queue.models import EpisodeContext, ScriptOutput
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.limits import script_char_limits, trim_to_limit
from src.script_gen.prompts import build_script_prompt


class ScriptState(TypedDict, total=False):
    context: EpisodeContext
    brief: str
    script_data: dict[str, Any]
    attempt: int
    min_chars: int
    max_chars: int
    error: str
    samples: list[str]
    previous: dict | None


MAX_ATTEMPTS = 5


def _validate_script(data: dict[str, Any], min_chars: int, max_chars: int) -> str | None:
    body = data.get("episode_only_script") or data.get("voiceover_script") or ""
    if not body.strip():
        return "empty voiceover_script"
    length = len(body.strip())
    if length < min_chars:
        return f"too short ({length} < {min_chars})"
    if length > max_chars + 50:
        return f"too long ({length} > {max_chars})"
    recap_phrases = ("पिछले एपिसोड", "पिछली कड़ी", "अब तक की कहानी")
    if any(p in body for p in recap_phrases):
        return "contains recap phrasing"
    return None


class ScriptGraphRunner:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.crew = ScriptCrew(config, logger)
        self.graph = self._build_graph()

    def generate(
        self,
        context: EpisodeContext,
        samples: list[str],
        previous: dict | None,
    ) -> ScriptOutput:
        min_chars, max_chars = script_char_limits(self.config)
        brief = build_script_prompt(
            novel_title=context.novel.title,
            author=context.novel.author,
            country=context.novel.country,
            episode_num=context.episode.episode_num,
            total_episodes=context.total_episodes,
            plot_beat=context.episode.plot_beat_summary,
            cumulative_synopsis=context.episode.cumulative_synopsis,
            sample_scripts=samples,
            previous_episode=previous,
            min_seconds=self.config.script_min_seconds,
            max_seconds=self.config.script_max_seconds,
            planned_hook=context.episode.planned_hook,
            planned_cliffhanger=context.episode.planned_cliffhanger,
            retention_angle=context.episode.retention_angle,
            min_chars=min_chars,
            max_chars=max_chars,
            novel_logline=context.novel.novel_logline,
            story_summary=context.novel.story_summary,
        )

        state: ScriptState = {
            "context": context,
            "brief": brief,
            "attempt": 0,
            "min_chars": min_chars,
            "max_chars": max_chars,
            "samples": samples,
            "previous": previous,
        }
        final = self.graph.invoke(state)
        data = final.get("script_data", {})
        body = data.get("episode_only_script") or data.get("voiceover_script", "")
        trimmed = trim_to_limit(body, max_chars)
        data["voiceover_script"] = trimmed
        data["episode_only_script"] = trimmed
        return ScriptOutput.from_dict(data)

    def _build_graph(self):
        graph = StateGraph(ScriptState)

        graph.add_node("write", self._write_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("refine", self._refine_node)

        graph.set_entry_point("write")
        graph.add_edge("write", "validate")
        graph.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {"refine": "refine", "done": END},
        )
        graph.add_edge("refine", "validate")
        return graph.compile()

    def _write_node(self, state: ScriptState) -> ScriptState:
        attempt = state.get("attempt", 0) + 1
        self.logger.info(f"script_graph | write attempt {attempt}")
        data = self.crew.write_script(
            state["brief"],
            state["min_chars"],
            state["max_chars"],
        )
        return {**state, "script_data": data, "attempt": attempt, "error": ""}

    def _validate_node(self, state: ScriptState) -> ScriptState:
        err = _validate_script(state["script_data"], state["min_chars"], state["max_chars"])
        return {**state, "error": err or ""}

    def _refine_node(self, state: ScriptState) -> ScriptState:
        err = state.get("error", "")
        self.logger.warn("script_graph", f"validation failed: {err} — refining")
        if "too short" in (err or ""):
            extra = (
                f"\n\nFIX REQUIRED: {err}. "
                f"The script is TOO SHORT. EXPAND to at least {state['min_chars']} characters. "
                f"Add specific plot events, character names, scene descriptions, dialogue beats. "
                f"Tell a complete mini-story for this episode. Cinematic dubbing tone. "
                f"Use dramatic pauses (…). NO vague filler."
            )
        else:
            extra = (
                f"\n\nFIX REQUIRED: {err}. "
                f"Rewrite with voiceover_script between {state['min_chars']}-{state['max_chars']} chars. "
                "NO recap. Named characters. Stronger hook. Sharper cliffhanger."
            )
        data = self.crew.refine_script(
            state["script_data"],
            extra,
            state["min_chars"],
            state["max_chars"],
        )
        return {**state, "script_data": data, "attempt": state.get("attempt", 0) + 1}

    def _route_after_validate(self, state: ScriptState) -> str:
        if not state.get("error"):
            return "done"
        if state.get("attempt", 0) >= MAX_ATTEMPTS:
            err = state.get("error", "")
            if "too short" in (err or ""):
                raise ValueError(
                    f"Script too short after {MAX_ATTEMPTS} attempts: {err}. "
                    f"Minimum {state['min_chars']} chars required for {self.config.script_min_seconds}s reel."
                )
            self.logger.warn("script_graph", "max attempts — using best effort with trim")
            return "done"
        return "refine"
