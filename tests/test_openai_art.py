"""Tests for Indian dark serial panel models and policy."""

from __future__ import annotations

from src.book_queue.models import ScriptOutput, StoryPanel
from src.script_gen.policy import check_script_policy
from src.visuals.openai_art import build_panel_prompt


def test_coerce_panels() -> None:
    script = ScriptOutput.from_dict(
        {
            "voiceover_script": "Test " * 200,
            "panels": [
                {
                    "dialogue": "Arey hamari beti aa gayi!",
                    "scene": "village courtyard reunion",
                    "speaker": "father",
                    "characters": ["Tanvi black tee", "father cream shirt"],
                    "bubble": "speech",
                }
            ],
        }
    )
    assert len(script.panels) == 1
    assert script.panels[0].dialogue.startswith("Arey")


def test_policy_blocks_explicit() -> None:
    err = check_script_policy({"voiceover_script": "explicit sex scene in bedroom"})
    assert err and "instagram policy" in err


def test_build_panel_prompt_includes_dialogue() -> None:
    panel = StoryPanel(
        dialogue="Mummy Papa!",
        scene="home courtyard",
        speaker="daughter Tanvi",
    )
    prompt = build_panel_prompt(panel, character_bible="Tanvi city girl")
    assert "Mummy Papa!" in prompt
    assert "speech bubble" in prompt.lower()
