"""Lightweight pipeline progress file — survives when SQLite cache misses on CI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineCheckpoint:
    novel_id: int = 0
    novel_title: str = ""
    completed_episodes: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "novel_title": self.novel_title,
            "completed_episodes": sorted(set(self.completed_episodes)),
        }

    @classmethod
    def from_dict(cls, data: dict) -> PipelineCheckpoint:
        return cls(
            novel_id=int(data.get("novel_id", 0)),
            novel_title=str(data.get("novel_title", "")),
            completed_episodes=[
                int(x) for x in data.get("completed_episodes", []) if str(x).isdigit()
            ],
        )


def checkpoint_path(data_dir: Path) -> Path:
    return data_dir / "checkpoint.json"


def load_checkpoint(data_dir: Path) -> PipelineCheckpoint | None:
    path = checkpoint_path(data_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cp = PipelineCheckpoint.from_dict(data)
        return cp if cp.completed_episodes else None
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def reset_checkpoint_for_novel(data_dir: Path, novel_id: int, novel_title: str) -> None:
    """Point checkpoint at a new novel with no completed episodes (used after --next-novel)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    cp = PipelineCheckpoint(novel_id=novel_id, novel_title=novel_title, completed_episodes=[])
    checkpoint_path(data_dir).write_text(
        json.dumps(cp.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_checkpoint(
    data_dir: Path,
    *,
    novel_id: int,
    novel_title: str,
    episode_num: int,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    existing = load_checkpoint(data_dir)
    if existing and existing.novel_id == novel_id:
        completed = set(existing.completed_episodes)
    else:
        completed = set()
    completed.add(episode_num)
    cp = PipelineCheckpoint(
        novel_id=novel_id,
        novel_title=novel_title,
        completed_episodes=sorted(completed),
    )
    checkpoint_path(data_dir).write_text(
        json.dumps(cp.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def apply_checkpoint_to_db(db, data_dir: Path, novel_id: int, novel_title: str) -> int:
    """Mark checkpointed episodes as generated in SQLite."""
    cp = load_checkpoint(data_dir)
    if not cp or not cp.completed_episodes:
        return 0

    if cp.novel_id and cp.novel_id != novel_id:
        if cp.novel_title and cp.novel_title.lower() != novel_title.lower():
            return 0

    return db.reconcile_episodes_to_checkpoint(novel_id, cp.completed_episodes)
