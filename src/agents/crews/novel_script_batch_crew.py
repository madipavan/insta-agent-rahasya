"""Summarize novel PDF (text extract) and batch-write all episode Hindi scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.crews.batch_validate import (
    find_duplicate_beats,
    normalize_script_dict,
    validate_script_dict,
)
from src.agents.llm_factory import get_chat_model
from src.book_queue.models import Novel
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.limits import script_char_limits
from src.utils.json_parse import parse_llm_json
from src.utils.llm_text import extract_llm_text

BATCH_SIZE = 3

SUMMARIZE_SYSTEM = """You are a Story Analyst for Instagram suspense reels.
Read the attached novel PDF and produce an original paraphrase summary — never quote the book.
Focus on characters, mysteries, stakes, and retention-worthy twists.
Output valid JSON only."""

PLAN_SYSTEM = """You are a Story Arc Strategist for binge Instagram thriller reels.
Design up to 12 UNIQUE episodes from the novel summary.
Rules:
- Each episode must cover NEW events only — never repeat another episode's plot.
- Do NOT recap or explain the previous episode in the next beat.
- Chain cliffhangers for retention, but open each episode in medias res.
- Name characters, places, and specific events.
- Original paraphrase only. Output valid JSON only."""

SCRIPT_BATCH_SYSTEM = """You write Hindi thriller reel voiceovers for Rahasya.exe.
Rules:
- Devanagari Hindi only for voiceover_script / episode_only_script.
- Do NOT explain or summarize the previous episode. No recap phrases.
- Each episode must be a NEW mini-story beat with hook → tension → cliffhanger.
- Named characters, cinematic dubbing tone, dramatic pauses (…).
- episode_only_script MUST equal voiceover_script.
- Hit the exact character limits. Output valid JSON only."""


class NovelScriptBatchCrew:
    """PDF → summarize (multimodal) → plan ≤12 beats → write all Hindi scripts."""

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.llm = get_chat_model(config, temperature=0.55, logger=logger)

    def build_full_package(
        self,
        novel: Novel,
        pdf_path: Path,
        episode_count: int,
        chapter_ranges: list[tuple[int, int]],
    ) -> dict[str, Any]:
        summary = self.summarize_novel_pdf(novel, pdf_path)
        arc = self.plan_episodes(novel, summary, episode_count, chapter_ranges)
        scripts = self.write_all_scripts(novel, summary, arc.get("episodes", []), episode_count)
        return {
            "novel_logline": arc.get("novel_logline") or summary.get("novel_logline", ""),
            "story_summary": arc.get("story_summary") or summary.get("story_summary", ""),
            "retention_strategy": arc.get("retention_strategy")
            or summary.get("retention_strategy", ""),
            "episodes": scripts,
        }

    def summarize_novel_pdf(self, novel: Novel, pdf_path: Path) -> dict[str, Any]:
        """Send the PDF file directly to Gemini (no local text extraction)."""
        prompt = (
            f"Novel: {novel.title} by {novel.author} ({novel.country})\n"
            "Read the attached PDF once and return JSON keys:\n"
            "novel_logline, story_summary (8-12 sentences, original paraphrase),\n"
            "retention_strategy (how to keep Instagram viewers bingeing),\n"
            "key_characters (array of names).\n"
            "Do not quote the book verbatim."
        )
        self.logger.info(f"batch_crew | summarize PDF directly ({pdf_path.name})")
        data = self._invoke_json_with_pdf(SUMMARIZE_SYSTEM, prompt, pdf_path)
        if data.get("story_summary") or data.get("novel_logline"):
            return data
        raise RuntimeError(
            "PDF summarize returned empty story bible — "
            "ensure GEMINI_API_KEY is set (PDF multimodal requires Gemini)."
        )

    def plan_episodes(
        self,
        novel: Novel,
        summary: dict[str, Any],
        episode_count: int,
        chapter_ranges: list[tuple[int, int]],
    ) -> dict[str, Any]:
        ranges_text = "\n".join(
            f"Ep {i}: chapters {s}-{e}" for i, (s, e) in enumerate(chapter_ranges, 1)
        )
        prompt = (
            f"Novel: {novel.title} by {novel.author}\n"
            f"Logline: {summary.get('novel_logline', '')}\n"
            f"Story summary: {summary.get('story_summary', '')}\n"
            f"Retention strategy: {summary.get('retention_strategy', '')}\n"
            f"Total episodes: {episode_count}\n"
            f"Chapter mapping:\n{ranges_text}\n\n"
            "Return JSON with keys: novel_logline, story_summary, retention_strategy, episodes.\n"
            "Each episode object MUST include: episode_num, plot_beat_summary, "
            "cumulative_synopsis (max 3 sentences, NO previous-episode recap), "
            "planned_hook, planned_cliffhanger, retention_angle.\n"
            "Every plot_beat_summary must be unique and specific."
        )
        self.logger.info("batch_crew | plan episode beats")
        arc = self._invoke_json(PLAN_SYSTEM, prompt)
        episodes = list(arc.get("episodes") or [])[:episode_count]
        # Pad / normalize numbering
        while len(episodes) < episode_count:
            i = len(episodes) + 1
            episodes.append(
                {
                    "episode_num": i,
                    "plot_beat_summary": f"Episode {i}: new pressure on the central mystery.",
                    "cumulative_synopsis": summary.get("story_summary", "")[:400],
                    "planned_hook": "",
                    "planned_cliffhanger": "",
                    "retention_angle": "raise stakes",
                }
            )
        for i, ep in enumerate(episodes, start=1):
            ep["episode_num"] = i
        dups = find_duplicate_beats(episodes)
        if dups:
            self.logger.warn("batch_crew", f"similar beats detected {dups} — refining uniqueness")
            fix_prompt = (
                "These episode beats are too similar. Rewrite ONLY the listed episodes so each "
                "has a UNIQUE plot_beat_summary, hook, and cliffhanger. Keep episode count.\n"
                f"Duplicates: {dups}\n"
                f"Current JSON:\n{json.dumps({'episodes': episodes}, ensure_ascii=False)}"
            )
            fixed = self._invoke_json(PLAN_SYSTEM, fix_prompt)
            fixed_eps = list(fixed.get("episodes") or episodes)[:episode_count]
            for i, ep in enumerate(fixed_eps, start=1):
                ep["episode_num"] = i
            episodes = fixed_eps
            arc["episodes"] = episodes
        else:
            arc["episodes"] = episodes
        if not arc.get("novel_logline"):
            arc["novel_logline"] = summary.get("novel_logline", "")
        if not arc.get("story_summary"):
            arc["story_summary"] = summary.get("story_summary", "")
        if not arc.get("retention_strategy"):
            arc["retention_strategy"] = summary.get("retention_strategy", "")
        return arc

    def write_all_scripts(
        self,
        novel: Novel,
        summary: dict[str, Any],
        episodes: list[dict[str, Any]],
        episode_count: int,
    ) -> list[dict[str, Any]]:
        min_chars, max_chars = script_char_limits(self.config)
        results: list[dict[str, Any]] = []
        prev_cliff = ""
        for start in range(0, episode_count, BATCH_SIZE):
            batch = episodes[start : start + BATCH_SIZE]
            batch_scripts = self._write_batch(
                novel=novel,
                summary=summary,
                batch=batch,
                total=episode_count,
                min_chars=min_chars,
                max_chars=max_chars,
                previous_cliffhanger=prev_cliff,
            )
            for ep, script in zip(batch, batch_scripts):
                merged = {
                    **ep,
                    "script": script,
                    "episode_num": ep.get("episode_num"),
                }
                results.append(merged)
                prev_cliff = script.get("cliffhanger") or ep.get("planned_cliffhanger") or prev_cliff
        # Ensure length
        return results[:episode_count]

    def _write_batch(
        self,
        novel: Novel,
        summary: dict[str, Any],
        batch: list[dict[str, Any]],
        total: int,
        min_chars: int,
        max_chars: int,
        previous_cliffhanger: str,
    ) -> list[dict[str, Any]]:
        briefs = []
        for ep in batch:
            briefs.append(
                {
                    "episode_num": ep.get("episode_num"),
                    "plot_beat_summary": ep.get("plot_beat_summary", ""),
                    "planned_hook": ep.get("planned_hook", ""),
                    "planned_cliffhanger": ep.get("planned_cliffhanger", ""),
                    "retention_angle": ep.get("retention_angle", ""),
                }
            )
        prompt = (
            f"Novel: {novel.title} by {novel.author} ({novel.country})\n"
            f"Logline: {summary.get('novel_logline') or novel.novel_logline}\n"
            f"Retention strategy: {summary.get('retention_strategy', '')}\n"
            f"Total episodes in series: {total}\n"
            f"Previous cliffhanger energy (do NOT retell/explain it): {previous_cliffhanger or 'N/A — series start'}\n\n"
            f"Write Hindi scripts for these episodes ONLY:\n{json.dumps(briefs, ensure_ascii=False)}\n\n"
            f"HARD LIMITS per episode: voiceover_script {min_chars}-{max_chars} Hindi chars.\n"
            "Return JSON: {\"scripts\": [ {episode_num, voiceover_script, episode_only_script, "
            "hook, cliffhanger, caption_hook, caption_teaser, static_post_text, "
            "stock_keywords, on_screen_text} ] }\n"
            "Do NOT explain the last episode. Each script must cover NEW events only."
        )
        nums = [int(ep.get("episode_num") or 0) for ep in batch]
        self.logger.info(f"batch_crew | write scripts eps {nums}")
        data = self._invoke_json(SCRIPT_BATCH_SYSTEM, prompt, max_tokens=8192)
        raw_scripts = data.get("scripts") or data.get("episodes") or []
        by_num = {
            int(s.get("episode_num") or 0): s
            for s in raw_scripts
            if isinstance(s, dict)
        }
        out: list[dict[str, Any]] = []
        for ep in batch:
            num = int(ep.get("episode_num") or 0)
            script = by_num.get(num) or (raw_scripts[len(out)] if len(raw_scripts) > len(out) else {})
            if not isinstance(script, dict):
                script = {}
            script = normalize_script_dict(script, max_chars)
            err = validate_script_dict(script, min_chars, max_chars)
            if err:
                self.logger.warn("batch_crew", f"ep {num} invalid ({err}) — rewriting")
                script = self._rewrite_one(
                    novel=novel,
                    summary=summary,
                    ep=ep,
                    total=total,
                    min_chars=min_chars,
                    max_chars=max_chars,
                    previous_cliffhanger=previous_cliffhanger,
                    error=err,
                    draft=script,
                )
            out.append(script)
            previous_cliffhanger = script.get("cliffhanger") or previous_cliffhanger
        return out

    def _rewrite_one(
        self,
        novel: Novel,
        summary: dict[str, Any],
        ep: dict[str, Any],
        total: int,
        min_chars: int,
        max_chars: int,
        previous_cliffhanger: str,
        error: str,
        draft: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = (
            f"FIX REQUIRED: {error}\n"
            f"Novel: {novel.title} by {novel.author}\n"
            f"Episode {ep.get('episode_num')}/{total}\n"
            f"Plot beat: {ep.get('plot_beat_summary', '')}\n"
            f"Hook: {ep.get('planned_hook', '')}\n"
            f"Cliffhanger: {ep.get('planned_cliffhanger', '')}\n"
            f"Retention: {ep.get('retention_angle', '')} | {summary.get('retention_strategy', '')}\n"
            f"Previous cliffhanger energy (do NOT explain/retell): {previous_cliffhanger or 'N/A'}\n"
            f"Draft JSON:\n{json.dumps(draft, ensure_ascii=False)}\n\n"
            f"Rewrite ONE script JSON with voiceover_script {min_chars}-{max_chars} chars. "
            "NO recap. NEW events only. episode_only_script = voiceover_script."
        )
        data = self._invoke_json(SCRIPT_BATCH_SYSTEM, prompt, max_tokens=4096)
        # Accept either wrapped or flat
        if "voiceover_script" not in data and isinstance(data.get("scripts"), list) and data["scripts"]:
            data = data["scripts"][0]
        script = normalize_script_dict(data, max_chars)
        # Final soft accept: if still short, keep normalized draft padded lightly via rewrite failure
        if validate_script_dict(script, max(0, min_chars - 30), max_chars):
            # Prefer rewritten if it has any body
            if not (script.get("voiceover_script") or "").strip():
                return normalize_script_dict(draft, max_chars)
        return script

    def _invoke_json_with_pdf(self, system: str, prompt: str, pdf_path: Path) -> dict[str, Any]:
        """Gemini multimodal: attach PDF bytes (no local text extraction)."""
        if not self.config.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY required to send novel PDF directly to the LLM")

        from google import genai
        from google.genai import types

        pdf_bytes = Path(pdf_path).read_bytes()
        if len(pdf_bytes) < 100:
            raise RuntimeError(f"PDF too small or empty: {pdf_path}")

        client = genai.Client(api_key=self.config.gemini_api_key)
        model = self.config.llm_model_gemini or "gemini-2.5-flash"
        self.logger.info(
            f"batch_crew | gemini PDF upload {len(pdf_bytes)} bytes via {model}"
        )
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                        types.Part.from_text(text=f"{system}\n\n{prompt}"),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=8192,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (response.text or "").strip()
        if not text:
            return {}
        try:
            return parse_llm_json(text)
        except Exception as exc:
            self.logger.warn("batch_crew", f"PDF summarize JSON parse failed: {exc}")
            return {}

    def _invoke_json(self, system: str, prompt: str, max_tokens: int = 8192) -> dict[str, Any]:
        _ = max_tokens
        resp = self.llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=prompt)]
        )
        text = extract_llm_text(resp)
        if not text:
            return {}
        try:
            return parse_llm_json(text)
        except Exception as exc:
            self.logger.warn("batch_crew", f"JSON parse failed: {exc}")
            return {}
