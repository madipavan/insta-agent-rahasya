"""Prompt templates for script generation."""

LEGAL_BLOCK = """
CRITICAL LEGAL CONSTRAINTS:
- NEVER reproduce the book's original prose verbatim, not even short quotes.
- Write an ORIGINAL paraphrase/retelling of plot events in your own words.
- Do NOT closely mirror the original chapter structure or sentence patterns.
- Tone: casual, punchy, Hinglish-friendly where natural — polished, never sloppy.
- VOICEOVER MUST BE IN HINDI (Devanagari script).
- Think movie-trailer voiceover — hook in 3 seconds, end on cliffhanger.
- NO recap. NO 'पिछले एपिसोड में'. Jump straight into today's action.
- Viewers scroll fast — every sentence must earn attention.
"""

SCRIPT_JSON_SCHEMA = """
Return ONLY valid JSON with these keys:
{
  "voiceover_script": "TODAY ONLY — Hindi Devanagari. HARD character limit given below. In medias res.",
  "episode_only_script": "Identical to voiceover_script.",
  "hook": "1 line on-screen hook Hindi",
  "cliffhanger": "final tease line Hindi — must match planned cliffhanger energy",
  "caption_hook": "caption opener (Hinglish ok)",
  "caption_teaser": "1 line teaser (Hinglish ok)",
  "static_post_text": "short punchy Hindi quote — 1 line max",
  "stock_keywords": ["english", "keywords", "cinematic"],
  "on_screen_text": ["hindi line1", "hindi line2", "hindi line3"]
}
"""


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
    min_seconds: int = 65,
    max_seconds: int = 82,
    planned_hook: str = "",
    planned_cliffhanger: str = "",
    retention_angle: str = "",
    min_chars: int = 0,
    max_chars: int = 0,
) -> str:
    samples = "\n---\n".join(sample_scripts[:3]) if sample_scripts else "No samples."

    if not min_chars or not max_chars:
        min_chars = min_seconds * 11
        max_chars = max_seconds * 11

    continuity_block = ""
    if episode_num > 1 and previous_episode:
        continuity_block = (
            f"\nWRITER CONTEXT (do NOT speak aloud):\n"
            f"Last cliffhanger: {previous_episode.get('cliffhanger', '')}\n"
            f"Pick up IN MEDIAS RES from today's beat. Zero recap.\n"
        )

    episode_brief = ""
    if planned_hook or planned_cliffhanger or retention_angle:
        episode_brief = (
            f"\nPRE-PLANNED EPISODE BRIEF (follow this arc):\n"
            f"Open with: {planned_hook or 'strong in-medias-res hook'}\n"
            f"End with: {planned_cliffhanger or 'cliffhanger tease'}\n"
            f"Retention angle: {retention_angle or 'suspense + stakes'}\n"
        )

    return (
        f"You write for Rahasya.exe — foreign thrillers Bollywood forgot.\n\n"
        f"{LEGAL_BLOCK}\n\n"
        f"STYLE (tone only):\n{samples}\n\n"
        f"Novel: {novel_title} by {author} ({country})\n"
        f"Episode {episode_num} of {total_episodes}\n"
        f"Today's plot beat: {plot_beat}\n"
        f"Background (never read aloud): {cumulative_synopsis}\n"
        f"{continuity_block}{episode_brief}\n"
        f"HARD LIMITS:\n"
        f"- voiceover_script: {min_chars}-{max_chars} characters ({min_seconds}-{max_seconds} sec spoken)\n"
        f"- Must fit Instagram carousel: max 10 slides\n"
        f"- Total reel under 90 seconds including intro/outro\n"
        f"- Punchy sentences. Cut filler. Strong hook. Sharp cliffhanger.\n"
        f"{SCRIPT_JSON_SCHEMA}"
    )
