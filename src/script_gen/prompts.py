"""Prompt templates for script generation."""

LEGAL_BLOCK = """
CRITICAL: Original Hindi paraphrase only. No verbatim book quotes.
Do NOT explain, summarize, or recap the previous episode. No recap phrases.
Each episode covers NEW events only — never repeat an earlier episode's plot.
Cinematic dubbing tone. In medias res. Devanagari script for voiceover.
"""

DUBBING_STYLE_BLOCK = """
Write like a Hindi thriller dubbing track: named characters, specific scenes, emotional pauses (…).
Build setup → tension → cliffhanger inside this episode only.
Use retention_strategy / retention_angle to keep viewers watching the next part.
"""

SCRIPT_JSON_SCHEMA = """
Return ONLY valid JSON with keys:
voiceover_script, episode_only_script, hook, cliffhanger, caption_hook, caption_teaser,
static_post_text, stock_keywords, on_screen_text
"""

_MAX_SAMPLE_CHARS = 700
_MAX_CONTEXT_CHARS = 450


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_script_prompt(
    novel_title: str,
    author: str,
    country: str,
    episode_num: int,
    total_episodes: int,
    plot_beat: str,
    cumulative_synopsis: str,
    sample_scripts: list[str],
    previous_episode: dict | None = None,
    min_seconds: int = 75,
    max_seconds: int = 80,
    planned_hook: str = "",
    planned_cliffhanger: str = "",
    retention_angle: str = "",
    min_chars: int = 0,
    max_chars: int = 0,
    novel_logline: str = "",
    story_summary: str = "",
    retention_strategy: str = "",
) -> str:
    sample_excerpt = "No samples."
    if sample_scripts:
        sample_excerpt = _clip(sample_scripts[0], _MAX_SAMPLE_CHARS)

    if not min_chars or not max_chars:
        min_chars = min_seconds * 11
        max_chars = max_seconds * 11

    plot_beat = _clip(plot_beat, _MAX_CONTEXT_CHARS)
    # Keep cumulative short — context only, not a recap to read aloud
    cumulative_synopsis = _clip(cumulative_synopsis, 220)
    novel_logline = _clip(novel_logline, 200)
    story_summary = _clip(story_summary, 280)
    retention_strategy = _clip(retention_strategy, 200)

    story_bible = ""
    if novel_logline or story_summary or retention_strategy:
        story_bible = (
            f"\nNOVEL BIBLE (context only — do NOT retell whole arc):\n"
            f"Logline: {novel_logline}\n"
            f"Arc (reference): {story_summary}\n"
            f"Retention strategy: {retention_strategy or 'hook fast, escalate, cliffhanger'}\n"
        )

    continuity_block = ""
    if episode_num > 1 and previous_episode:
        cliff = _clip(previous_episode.get("cliffhanger", ""), 160)
        continuity_block = (
            f"\nCONTINUITY (energy only — DO NOT explain last episode):\n"
            f"Open in medias res from this cliffhanger energy: {cliff or 'unresolved danger'}\n"
            f"Jump into THIS episode's new events immediately.\n"
        )
    elif episode_num == 1:
        continuity_block = (
            "\nEPISODE 1: Hook in 3 seconds. Introduce hero + mystery. Strong cliffhanger.\n"
        )

    episode_brief = ""
    if planned_hook or planned_cliffhanger or retention_angle:
        episode_brief = (
            f"\nEPISODE BRIEF:\n"
            f"Open: {_clip(planned_hook, 160) or 'strong hook'}\n"
            f"End: {_clip(planned_cliffhanger, 160) or 'cliffhanger'}\n"
            f"Angle: {_clip(retention_angle, 160) or 'suspense'}\n"
        )

    return (
        f"You write for Rahasya.exe — foreign thrillers Bollywood forgot.\n\n"
        f"{LEGAL_BLOCK}\n"
        f"{DUBBING_STYLE_BLOCK}\n\n"
        f"STYLE REFERENCE (tone only):\n{sample_excerpt}\n\n"
        f"Novel: {novel_title} by {author} ({country})\n"
        f"Episode {episode_num}/{total_episodes}\n"
        f"Plot beat (THIS episode only): {plot_beat}\n"
        f"Position in story (do not narrate as recap): {cumulative_synopsis}\n"
        f"{story_bible}{continuity_block}{episode_brief}\n"
        f"HARD LIMITS: voiceover_script {min_chars}-{max_chars} Hindi chars "
        f"({min_seconds}-{max_seconds}s spoken). episode_only_script = voiceover_script.\n"
        f"{SCRIPT_JSON_SCHEMA}"
    )
