"""CrewAI-style multi-agent script writing via LangChain."""

from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.llm_factory import get_chat_model
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.json_parse import parse_llm_json
from src.utils.llm_text import extract_llm_text
from src.utils.llm_errors import is_llm_limit_error

WRITER_SYSTEM = """You are a Hindi Suspense Scriptwriter for Rahasya.exe Instagram reels.
Write ORIGINAL paraphrase only — never quote the book.
Output valid JSON only.

You write like a Hindi thriller film dubbing artist — emotional, tense, cinematic.
Every script is a complete mini-story: specific characters, places, events, stakes.
NEVER write vague filler like "एक आदमी जो अपनी जान बचाने की कोशिश कर रहा है".
Name the hero. Describe what happened. Build tension scene by scene.
Use ellipsis (…) for dramatic pauses before reveals.
Add emotional beats — fear, suspense, shock — not flat narration.
Do NOT explain or recap the previous episode. Cover NEW events only.
HIT the minimum character count — short scripts are rejected."""

EDITOR_SYSTEM = """You are a Retention Editor for Hindi thriller reels.
Your job is to EXPAND thin scripts and sharpen hooks/cliffhangers.
If the script is under the minimum character count, ADD more specific story beats.
Cut only true filler. Keep character names, scene details, emotional beats.
Enforce character limits exactly. Output valid JSON only. NO recap phrases.
Do NOT add previous-episode explanations. Keep only THIS episode's new events.
Scripts must sound like film dubbing — not a robot reading words."""

REFINE_EDITOR_SYSTEM = """You are a Retention Editor for Hindi thriller reels.
Follow the FIX REQUIRED instruction exactly:
- If too short: expand with specific plot beats (never vague filler).
- If too long: shorten — cut redundant lines, keep hook, key beats, cliffhanger.
Never add recap. Output valid JSON only. Enforce character limits exactly."""

MAX_LLM_ATTEMPTS = 3


class ScriptCrew:
    """Writer + Editor agents (CrewAI-style sequential crew via LangChain)."""

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.writer_llm = get_chat_model(config, temperature=0.8, logger=logger)
        self.editor_llm = get_chat_model(config, temperature=0.4, logger=logger)

    def write_script(self, brief: str, min_chars: int, max_chars: int) -> dict[str, Any]:
        self.logger.info("script_crew | writer agent")
        draft = self._invoke_json(self.writer_llm, WRITER_SYSTEM, brief, "writer")

        edit_brief = self._edit_brief(draft, min_chars, max_chars)
        self.logger.info("script_crew | editor agent")
        return self._invoke_json(
            self.editor_llm,
            EDITOR_SYSTEM,
            edit_brief,
            "editor",
            fallback=draft,
        )

    def refine_script(
        self,
        draft: dict[str, Any],
        fix_instruction: str,
        min_chars: int,
        max_chars: int,
        *,
        shorten: bool = False,
    ) -> dict[str, Any]:
        """Edit an existing draft in-place (used by validation refine loop)."""
        self.logger.info("script_crew | editor refine")
        edit_brief = (
            f"{fix_instruction.strip()}\n\n"
            f"{self._edit_brief(draft, min_chars, max_chars, shorten=shorten)}"
        )
        return self._invoke_json(
            self.editor_llm,
            REFINE_EDITOR_SYSTEM,
            edit_brief,
            "editor-refine",
            fallback=draft,
        )

    def _edit_brief(
        self,
        draft: dict[str, Any],
        min_chars: int,
        max_chars: int,
        *,
        shorten: bool = False,
    ) -> str:
        if shorten:
            return (
                f"Edit this script JSON. HARD LIMIT: voiceover_script at most {max_chars} chars.\n"
                f"The script is TOO LONG — CUT and tighten. Remove redundant sentences and filler.\n"
                f"Keep the hook, essential plot beats, and cliffhanger. Do NOT add new scenes.\n"
                f"episode_only_script = voiceover_script.\n"
                f"NO recap. Named characters. Cinematic dubbing tone.\n\n"
                f"{json.dumps(draft, ensure_ascii=False)}"
            )
        return (
            f"Edit this script JSON. HARD LIMIT: voiceover_script {min_chars}-{max_chars} chars.\n"
            f"If under {min_chars} chars, EXPAND with more specific plot events and dialogue beats.\n"
            f"episode_only_script = voiceover_script.\n"
            f"NO recap. Named characters. Cinematic dubbing tone. Dramatic pauses with …\n"
            f"Strong hook. Sharp cliffhanger.\n\n"
            f"{json.dumps(draft, ensure_ascii=False)}"
        )

    def _invoke_json(
        self,
        llm: BaseChatModel,
        system: str,
        user: str,
        label: str,
        *,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_preview = ""
        for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
            try:
                resp = llm.invoke([
                    SystemMessage(content=system),
                    HumanMessage(content=user),
                ])
            except Exception as exc:
                if is_llm_limit_error(exc):
                    self.logger.warn("script_crew", f"{label} rate limited — retrying")
                    time.sleep(10 * attempt)
                    continue
                raise
            text = extract_llm_text(resp)
            if not text:
                self.logger.warn("script_crew", f"{label} empty response (attempt {attempt})")
                continue
            last_preview = text[:200]
            try:
                return parse_llm_json(text)
            except json.JSONDecodeError:
                self.logger.warn("script_crew", f"{label} invalid JSON (attempt {attempt})")

        if fallback is not None:
            self.logger.warn("script_crew", f"{label} failed — using previous draft")
            return fallback

        preview = last_preview or "<empty>"
        raise ValueError(f"{label} failed after {MAX_LLM_ATTEMPTS} attempts: {preview}")
