"""Reset rahasya.db for a single active novel with completed episodes already posted."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.book_queue.pacing import chapter_ranges, estimate_episode_count
from src.book_queue.store import Database
from src.config import load_config

DEFAULT_NOVEL = {
    "title": "The Thirty-Nine Steps",
    "author": "John Buchan",
    "country": "UK",
    "chapter_count": 10,
    "public_domain": True,
    "source_link": "https://www.gutenberg.org/ebooks/558",
    "adaptation_checked": True,
}


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def _clean_output(output_dir: Path, novel_title: str | None = None) -> int:
    removed = 0
    for sub in ("work", "review", "approved", "posted", "ready_to_upload"):
        base = output_dir / sub
        if not base.exists():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            if novel_title is None or _slug(novel_title) in child.name.lower():
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
    return removed


def bootstrap(
    *,
    completed_episodes: list[int],
    clean_output: bool = True,
    clean_all_output: bool = False,
    novel: dict | None = None,
) -> None:
    config = load_config()
    db_path = config.path("db_path")
    data_dir = config.path("data_dir")
    output_dir = config.path("output_dir")
    novel_info = {**DEFAULT_NOVEL, **(novel or {})}

    if db_path.exists():
        db_path.unlink()

    db = Database(db_path)
    novel_id = db.add_novel(
        title=novel_info["title"],
        author=novel_info["author"],
        country=novel_info["country"],
        chapter_count=novel_info["chapter_count"],
        public_domain=novel_info["public_domain"],
        source_link=novel_info["source_link"],
        adaptation_checked=novel_info["adaptation_checked"],
        status="active",
    )

    episode_count = estimate_episode_count(novel_info["chapter_count"])
    completed = set(completed_episodes)
    ranges = chapter_ranges(novel_info["chapter_count"], episode_count)

    for ep_num, (start, end) in enumerate(ranges, start=1):
        status = "generated" if ep_num in completed else "pending"
        db.add_episode(
            novel_id=novel_id,
            episode_num=ep_num,
            chapter_start=start,
            chapter_end=end,
            plot_beat_summary=f"Episode {ep_num}: chapters {start}-{end}.",
            cumulative_synopsis=f"Through episode {ep_num}.",
            status=status,
        )

    max_done = max(completed) if completed else 0
    with db._connect() as conn:
        conn.execute(
            "UPDATE novels SET current_episode = ? WHERE id = ?",
            (max_done, novel_id),
        )

    checkpoint = {
        "novel_id": novel_id,
        "novel_title": novel_info["title"],
        "completed_episodes": sorted(completed),
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "checkpoint.json").write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    removed = 0
    if clean_output:
        removed = _clean_output(
            output_dir, None if clean_all_output else novel_info["title"]
        )

    print(f"DB reset: {novel_info['title']} (id={novel_id})")
    print(f"Episodes: {episode_count} total, completed {sorted(completed)}")
    print(f"Next pending: ep {max_done + 1 if max_done < episode_count else 'none'}")
    if clean_output:
        print(f"Removed {removed} output folder(s) for this novel")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a fresh pipeline database.")
    parser.add_argument(
        "--completed",
        default="1,2",
        help="Comma-separated episode numbers already posted (default: 1,2)",
    )
    parser.add_argument(
        "--no-clean-output",
        action="store_true",
        help="Keep existing output folders",
    )
    parser.add_argument(
        "--all-output",
        action="store_true",
        help="Remove every episode folder under output/ (full reset)",
    )
    args = parser.parse_args()
    completed = [int(x.strip()) for x in args.completed.split(",") if x.strip()]
    bootstrap(
        completed_episodes=completed,
        clean_output=not args.no_clean_output,
        clean_all_output=args.all_output,
    )


if __name__ == "__main__":
    main()
