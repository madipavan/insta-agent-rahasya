"""Shared script-craft rules for writer / editor / batch / planner prompts."""

SCRIPT_CRAFT_RULES = """
RAHASYA.EXE SCRIPT RULES (non-negotiable):

FORMAT
- Original Indian dark serial ONLY — NOT classic novels, NOT foreign settings, NOT book adaptations.
- Genre engine: affair tension, cheat/blackmail, crime, revenge, family scandal — Instagram-safe (suggestive dialogue, not explicit visuals).
- Setting: always India (Delhi, Lucknow, small town, joint family). Indian names only.

SPOKEN LANGUAGE
- Spoken Hinglish: short sentences, everyday Hindi in Devanagari + common English words
  (police, phone, plan, twist, file, warning, secret).
- Sound like a tense thriller narrator for Reels, NOT literary prose or formal news Hindi.

RETENTION (every episode)
- Hook 0–2s = shock, danger, or direct question. No "एक दिन…", no slow backstory.
- New tension every ~5–7s → mid-twist → cliffhanger in last 8s.
- Cold-open every episode (viewer may not have seen Part 1). Do NOT recap previous episode.
- caption_hook or caption_teaser MUST end with a plot question (comment bait with ?).

PANELS (for comic Reel visuals)
- Output panels[] with 10–12 items synced to voiceover beats (~6–8s each).
- Each panel: dialogue = short Roman Hinglish bubble text (4–12 words), scene, speaker, characters.
- bubble = "speech" or "thought". One bubble per panel unless two speakers in same frame.
- dialogue is what appears INSIDE the comic bubble (Roman script, not Devanagari).

CAPTION
- Brand hashtag spelling is exactly #RahasyaExe (never rahaysaexe / rahasyaexe typos).

INSTAGRAM SAFETY
- Affair/cheat as plot tension in dialogue only. No explicit sex, nudity, minors, graphic violence, drugging visuals.
- Scenes: market, home, kirana, street, office — not bedroom intimacy.

BILINGUAL FIELDS
- Also output english_voiceover: tight English parallel of the spoken Hinglish (same beats).
- english_on_screen: short English hook matching on_screen_text (for mute viewers).
- on_screen_text[0] = same hook phrase as first narration line (short, mute-readable).
""".strip()
