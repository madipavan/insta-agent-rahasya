"""CrewAI-style multi-agent script writing via LangChain."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.llm_factory import get_chat_model
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.utils.json_parse import parse_llm_json

WRITER_SYSTEM = """You are a Hindi Suspense Scriptwriter for Rahasya.exe Instagram reels.
Write ORIGINAL paraphrase only — never quote the book.
Output valid JSON only. Movie-trailer energy. Devanagari Hindi."""

EDITOR_SYSTEM = """You are a Retention Editor. Trim filler. Sharpen hooks and cliffhangers.
Enforce character limits exactly. Output valid JSON only. NO recap phrases."""


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
        draft = parse_llm_json(str(writer_resp.content))

        edit_brief = (
            f"Edit this script JSON. HARD LIMIT: voiceover_script {min_chars}-{max_chars} chars.\n"
            f"episode_only_script = voiceover_script.\n"
            f"NO recap. Strong hook. Sharp cliffhanger.\n\n"
            f"{json.dumps(draft, ensure_ascii=False)}"
        )
        self.logger.info("script_crew | editor agent")
        editor_resp = self.editor_llm.invoke([
            SystemMessage(content=EDITOR_SYSTEM),
            HumanMessage(content=edit_brief),
        ])
        return parse_llm_json(str(editor_resp.content))
