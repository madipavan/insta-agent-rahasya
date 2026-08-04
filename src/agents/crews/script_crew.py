"""CrewAI-style multi-agent script writing via LangChain."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.llm_factory import get_chat_model
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.json_parse import parse_llm_json
from src.utils.llm_text import extract_llm_text

WRITER_SYSTEM = """You are a Hindi Suspense Scriptwriter for Rahasya.exe Instagram reels.
Write ORIGINAL paraphrase only — never quote the book.
Output valid JSON only.

You write like a Hindi thriller film dubbing artist — emotional, tense, cinematic.
Every script is a complete mini-story: specific characters, places, events, stakes.
NEVER write vague filler like "एक आदमी जो अपनी जान बचाने की कोशिश कर रहा है".
Name the hero. Describe what happened. Build tension scene by scene.
Use ellipsis (…) for dramatic pauses before reveals.
HIT the minimum character count — short scripts are rejected."""

EDITOR_SYSTEM = """You are a Retention Editor for Hindi thriller reels.
Your job is to EXPAND thin scripts and sharpen hooks/cliffhangers.
If the script is under the minimum character count, ADD more specific story beats.
Cut only true filler. Keep character names, scene details, emotional beats.
Enforce character limits exactly. Output valid JSON only. NO recap phrases.
Scripts must sound like film dubbing — not a robot reading words."""


class ScriptCrew:
    """Writer + Editor agents (CrewAI-style sequential crew via LangChain)."""

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.writer_llm = get_chat_model(config, temperature=0.8)
        self.editor_llm = get_chat_model(config, temperature=0.4)

    def write_script(self, brief: str, min_chars: int, max_chars: int) -> dict[str, Any]:
        self.logger.info("script_crew | writer agent")
        writer_resp = self.writer_llm.invoke([
            SystemMessage(content=WRITER_SYSTEM),
            HumanMessage(content=brief),
        ])
        draft = parse_llm_json(extract_llm_text(writer_resp))

        edit_brief = (
            f"Edit this script JSON. HARD LIMIT: voiceover_script {min_chars}-{max_chars} chars.\n"
            f"If under {min_chars} chars, EXPAND with more specific plot events and dialogue beats.\n"
            f"episode_only_script = voiceover_script.\n"
            f"NO recap. Named characters. Cinematic dubbing tone. Dramatic pauses with …\n"
            f"Strong hook. Sharp cliffhanger.\n\n"
            f"{json.dumps(draft, ensure_ascii=False)}"
        )
        self.logger.info("script_crew | editor agent")
        editor_resp = self.editor_llm.invoke([
            SystemMessage(content=EDITOR_SYSTEM),
            HumanMessage(content=edit_brief),
        ])
        editor_text = extract_llm_text(editor_resp)
        if not editor_text:
            self.logger.warn("script_crew", "editor returned empty response — using writer draft")
            return draft
        try:
            return parse_llm_json(editor_text)
        except json.JSONDecodeError:
            self.logger.warn("script_crew", "editor JSON invalid — using writer draft")
            return draft
