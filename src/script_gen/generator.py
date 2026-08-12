"""Script generation via LangGraph + CrewAI (or saved upfront scripts)."""

from __future__ import annotations

import json

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

    def generate(self, context: EpisodeContext, *, regen_script: bool = False) -> ScriptOutput:
        if not regen_script:
            saved = self._load_saved_script(context)
            if saved is not None:
                spoken = saved.episode_script()
                if spoken:
                    self.logger.start(
                        "script_gen",
                        f"ep {context.episode.episode_num} (saved script_json)",
                    )
                    self.logger.ok("script_gen", f"{len(spoken)} chars (prewritten)")
                    return saved
        elif regen_script:
            self.logger.info(
                f"script_gen | --regen-script: ignoring saved script_json for ep {context.episode.episode_num}"
            )

        self.logger.start("script_gen", f"ep {context.episode.episode_num} (langgraph+crewai)")
        samples = self._load_sample_scripts()
        # Do not inject previous voiceover for recap — only cliffhanger energy if needed by live path.
        previous = self.db.get_previous_episode_context(
            context.novel.id,
            context.episode.episode_num,
        )
        if previous:
            previous = {
                "cliffhanger": previous.get("cliffhanger", ""),
                "voiceover_excerpt": "",
                "summary": "",
            }
        script = self.runner.generate(context, samples, previous)
        spoken = script.episode_script()
        if not spoken:
            raise ValueError("Script generation returned empty voiceover_script")
        self.logger.ok("script_gen", f"{len(spoken)} chars")
        return script

    def _load_saved_script(self, context: EpisodeContext) -> ScriptOutput | None:
        raw = (
            context.episode.script_json
            or self.db.get_episode_script_json(context.novel.id, context.episode.episode_num)
        )
        if not raw or not str(raw).strip():
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.logger.warn("script_gen", "saved script_json is invalid JSON — regenerating")
            return None
        if not isinstance(data, dict):
            return None
        # Unwrap nested {"script": {...}} if present
        if "voiceover_script" not in data and isinstance(data.get("script"), dict):
            data = data["script"]
        script = ScriptOutput.from_dict(data)
        if not script.episode_script():
            return None
        style = getattr(self.config, "stock_style_tag", "") or ""
        if style and not any(
            style.lower() in k.lower() or k.lower() in style.lower()
            for k in script.stock_keywords
        ):
            script.stock_keywords = list(script.stock_keywords) + [style]
        return script

    def _load_sample_scripts(self) -> list[str]:
        scripts_dir = self.config.path("sample_scripts")
        if not scripts_dir.exists():
            return []
        preferred = scripts_dir / "example_00_hook_hinglish.txt"
        paths = sorted(scripts_dir.glob("*.txt"))
        if preferred.exists():
            paths = [preferred] + [p for p in paths if p != preferred]
        for path in paths:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return [text[:700]]
        return []

    def format_caption(self, context: EpisodeContext, script: ScriptOutput) -> str:
        from src.hashtags.brand import DEFAULT_BRAND_HASHTAG, normalize_brand_hashtag

        template = self.config.caption_template or (
            "{caption_hook}\n\n{caption_teaser}\n\n"
            "Part {episode}/{total} of \"{novel_title}\"\n{cta}\n\n{hashtags}"
        )
        locked = getattr(self.config, "brand_hashtag", DEFAULT_BRAND_HASHTAG) or DEFAULT_BRAND_HASHTAG
        hashtags, _ = normalize_brand_hashtag(self.config.hashtags, locked)
        caption = template.format(
            caption_hook=script.caption_hook,
            caption_teaser=script.caption_teaser,
            episode=context.episode.episode_num,
            total=context.total_episodes,
            novel_title=context.novel.title,
            cta=self.config.cta,
            hashtags=hashtags,
        )
        caption, _ = normalize_brand_hashtag(caption, locked)
        return caption
