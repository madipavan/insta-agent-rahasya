"""Tests for Indian dark serial queue migration."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from src.book_queue.models import Novel
from src.book_queue.store import Database
from src.episode_planner.planner import EpisodePlanner
from src.pipeline.logger import PipelineLogger


def test_archive_non_serial_novels() -> None:
    fd, raw_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(raw_path)
    db = Database(db_path)
    try:
        legacy_id = db.add_novel("Old Book", "Erskine Childers", status="active")
        serial_id = db.add_novel("Gaon Wapas", "Rahasya Original", status="queued")
        archived = db.archive_non_serial_novels()
        assert archived == 1
        legacy = db.get_novel(legacy_id)
        serial = db.get_novel(serial_id)
        assert legacy is not None and legacy.status == "archived"
        assert serial is not None and serial.status == "queued"
    finally:
        del db
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def test_seed_bible_outline_builds_episodes() -> None:
    from src.config import load_config

    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    planner = EpisodePlanner.__new__(EpisodePlanner)
    planner.config = config
    planner.logger = logger
    novel = Novel(
        id=1,
        title="Test Serial",
        author="Rahasya Original",
        country="India",
        chapter_count=10,
        public_domain=False,
        source_link="",
        adaptation_checked=True,
        estimated_episodes=8,
        status="active",
        novel_logline="Shock hook logline.",
        story_summary="Full story summary for Indian dark serial.",
        retention_strategy="Retention hooks every episode.",
    )
    ranges = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (1, 2), (3, 4), (5, 6)]
    package = planner._outline_from_seed_bible(novel, 8, ranges)
    assert len(package["episodes"]) == 8
    assert package["novel_logline"] == novel.novel_logline
    assert "Test Serial" in package["episodes"][0]["plot_beat_summary"]
