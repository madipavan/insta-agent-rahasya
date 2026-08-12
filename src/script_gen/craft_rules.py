"""Shared script-craft rules for writer / editor / batch / planner prompts."""

SCRIPT_CRAFT_RULES = """
RAHASYA.EXE SCRIPT RULES (non-negotiable):

SPOKEN LANGUAGE
- Spoken Hinglish: short sentences, everyday Hindi in Devanagari + common English words
  (police, phone, plan, twist, file, warning, secret).
- Sound like a tense thriller narrator, NOT literary book prose or formal news Hindi.

HOOK (first narration line + mute-readable on-screen text)
- First line = danger, shock, or a direct question. Mute-readable in under 2 seconds.
- BANNED openings: "एक दिन…", "कुछ समय पहले…", "यह कहानी है…", pure time/place/backstory
  before tension, slow scene-setting without stakes.
- on_screen_text[0] MUST be that same hook phrase (short), NEVER a generic summary like
  "एक रहस्यमयी मुलाकात" / "mysterious meeting".

SETTING
- Named classic novel (Woman in White, Thirty-Nine Steps, etc.): KEEP original setting + names.
  Frame in hook/caption as a famous world classic
  ("दुनिया के सबसे मशहूर रहस्यमयी उपन्यासों में से एक…").
- Original / loosely-inspired stories: Indian city, Indian names, Indian institutions.

PACING / STRUCTURE
- Hook 0–2s → new tension every ~5–7s → cliffhanger or choice/prediction.
- No two expository sentences back to back. Cold-open every episode (viewer may not have seen Part 1).
- Do NOT recap previous episode.

CAPTION
- caption_hook or caption_teaser MUST end with a plot question (comment bait with ?).
- Brand hashtag spelling is exactly #RahasyaExe (never rahaysaexe / rahasyaexe typos).

STOCK / VISUALS
- stock_keywords = actual setting + actual visual subject + style tag.
  NEVER mood-only (cinematic / dark / mystery alone).
- on_screen_text is the hook, not a theme label.

BILINGUAL FIELDS
- Also output english_voiceover: tight English parallel of the spoken Hinglish (same beats).
- english_on_screen: short English hook matching on_screen_text (for mute viewers).
""".strip()
