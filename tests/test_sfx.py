"""Tests for retention SFX placement logic."""

from src.visuals.sfx import build_sfx_placements


def test_build_sfx_placements_includes_hook_and_cliffhanger():
    placements = build_sfx_placements(80.0, 4)
    types = [p.sfx_type for p in placements]
    assert types[0] == "hook_impact"
    assert "cliffhanger_rumble" in types
    assert types.count("whoosh_short") == 3


def test_build_sfx_placements_single_clip():
    placements = build_sfx_placements(60.0, 1)
    assert len(placements) == 2
    assert placements[0].sfx_type == "hook_impact"
    assert placements[1].sfx_type == "cliffhanger_rumble"


def test_build_sfx_placements_zero_duration():
    assert build_sfx_placements(0.0, 4) == []
