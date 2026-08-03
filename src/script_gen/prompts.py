"""Prompt templates for script generation."""

LEGAL_BLOCK = """
CRITICAL LEGAL CONSTRAINTS:
- NEVER reproduce the book's original prose verbatim, not even short quotes.
- Write an ORIGINAL paraphrase/retelling of plot events in your own words.
- Do NOT closely mirror the original chapter structure or sentence patterns.
- Tone: cinematic Hindi narration — like a thriller film dubbing track, not a news reader.
- VOICEOVER MUST BE IN HINDI (Devanagari script).
- NO recap. NO 'पिछले एपिसोड में'. Jump straight into today's action.
- Viewers scroll fast — every sentence must earn attention.
"""

DUBBING_STYLE_BLOCK = """
DUBBING / PERFORMANCE STYLE (write for voice actor delivery):
- Narrate like a Hindi thriller film dubbing artist — emotion, tension, breath.
- Use short punchy lines AND longer dramatic sentences. Vary rhythm.
- Add natural pauses with ellipsis (…) after shocking reveals or before cliffhangers.
- Name characters, places, objects — never say "एक आदमी" when you know his name.
- Show specific scenes: what happened, who said what, what was found, where they ran.
- Build a mini-story arc WITHIN this episode: setup → rising tension → peak → cliffhanger.
- Episode 2+ must feel like a direct continuation — open on the consequence of last cliffhanger.
- Do NOT be vague ("tension rises", "danger lurks") — tell WHAT happened.
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
    min_seconds: int = 75,
    max_seconds: int = 80,
    planned_hook: str = "",
    planned_cliffhanger: str = "",
    retention_angle: str = "",
    min_chars: int = 0,
    max_chars: int = 0,
    novel_logline: str = "",
    story_summary: str = "",
) -> str:
    samples = "\n---\n".join(sample_scripts[:3]) if sample_scripts else "No samples."

    if not min_chars or not max_chars:
        min_chars = min_seconds * 11
        max_chars = max_seconds * 11

    story_bible = ""
    if novel_logline or story_summary:
        story_bible = (
            f"\nNOVEL STORY BIBLE (context only — do NOT read aloud):\n"
            f"Logline: {novel_logline}\n"
            f"Full arc: {story_summary}\n"
            f"Episode {episode_num} of {total_episodes} — tell THIS chapter of the arc.\n"
        )

    continuity_block = ""
    if episode_num > 1 and previous_episode:
        continuity_block = (
            f"\nCONTINUITY (do NOT recap aloud — weave into opening action):\n"
            f"Last cliffhanger: {previous_episode.get('cliffhanger', '')}\n"
            f"Where we left off: {previous_episode.get('voiceover_excerpt', '')[:200]}\n"
            f"Open IN MEDIAS RES — viewer must feel the story never stopped.\n"
        )
    elif episode_num == 1:
        continuity_block = (
            f"\nEPISODE 1 — SERIES PREMIERE:\n"
            f"Hook the audience in 3 seconds. Introduce protagonist and central mystery.\n"
            f"Set the world. End on a cliffhanger that makes them NEED episode 2.\n"
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
        f"{LEGAL_BLOCK}\n"
        f"{DUBBING_STYLE_BLOCK}\n\n"
        f"STYLE REFERENCE (tone + length — match this energy and depth):\n{samples}\n\n"
        f"Novel: {novel_title} by {author} ({country})\n"
        f"Episode {episode_num} of {total_episodes}\n"
        f"Today's plot beat: {plot_beat}\n"
        f"Story so far (never read aloud): {cumulative_synopsis}\n"
        f"{story_bible}{continuity_block}{episode_brief}\n"
        f"HARD LIMITS:\n"
        f"- voiceover_script: MINIMUM {min_chars} characters, maximum {max_chars} "
        f"({min_seconds}-{max_seconds} sec when spoken)\n"
        f"- Scripts under {min_chars} chars will be REJECTED. Fill the full runtime with story.\n"
        f"- Must fit Instagram carousel: max 10 slides\n"
        f"- Cinematic dubbing narration. Specific events. Named characters. Emotional delivery.\n"
        f"{SCRIPT_JSON_SCHEMA}"
    )
