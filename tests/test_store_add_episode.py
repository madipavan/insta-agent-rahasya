"""Regression: LLM nested objects must not crash SQLite add_episode binds."""

from __future__ import annotations

import json
from pathlib import Path

from src.book_queue.store import Database, _as_sqlite_text


def test_as_sqlite_text_extracts_common_keys() -> None:
    assert _as_sqlite_text({"hook": "Danger at the pier?"}) == "Danger at the pier?"
    assert _as_sqlite_text({"text": "  cliff  "}) == "cliff"
    assert _as_sqlite_text(["a", "b"]) == json.dumps(["a", "b"], ensure_ascii=False)
    assert _as_sqlite_text(None) == ""
    assert _as_sqlite_text("plain") == "plain"


def test_add_episode_accepts_dict_valued_fields(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    novel_id = db.add_novel(
        title="The Moonstone",
        author="Wilkie Collins",
        country="UK",
        chapter_count=20,
    )

    ep_id = db.add_episode(
        novel_id=novel_id,
        episode_num=1,
        chapter_start=1,
        chapter_end=3,
        plot_beat_summary={"summary": "Franklin arrives; the diamond is missing."},
        cumulative_synopsis={"text": "Setup: diamond vanishes from the Verinder house."},
        status="pending",
        planned_hook={"hook": "Who stole the Moonstone?"},
        planned_cliffhanger={"cliffhanger": "A footprint in the wet sand."},
        retention_angle={"angle": "Everyone is a suspect."},
        script_json={"voiceover_script": "placeholder", "hook": "x"},
    )

    assert ep_id > 0
    ep = db.get_episode(novel_id, 1)
    assert ep is not None
    assert isinstance(ep.planned_hook, str)
    assert ep.planned_hook == "Who stole the Moonstone?"
    assert ep.planned_cliffhanger == "A footprint in the wet sand."
    assert ep.retention_angle == "Everyone is a suspect."
    assert ep.plot_beat_summary == "Franklin arrives; the diamond is missing."
    assert "diamond vanishes" in ep.cumulative_synopsis
    assert isinstance(ep.script_json, str)
    assert "voiceover_script" in ep.script_json
