"""Set DB to post--next-novel state: Thirty-Nine Steps abandoned, Riddle active."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.book_queue.checkpoint import reset_checkpoint_for_novel
from src.book_queue.pacing import chapter_ranges, estimate_episode_count
from src.book_queue.store import Database
from src.config import load_config

SKIP_TITLE = "The Thirty-Nine Steps"
NEXT_TITLE = "The Riddle of the Sands"


def main() -> None:
    config = load_config()
    db = Database(config.path("db_path"))
    db.import_seed_file(config.path("novels_seed"))

    all_novels = db.list_novels()
    skip = next((n for n in all_novels if n.title == SKIP_TITLE), None)
    nxt = next((n for n in all_novels if n.title == NEXT_TITLE), None)
    if not skip:
        raise SystemExit(f"Novel not found: {SKIP_TITLE!r}")
    if not nxt:
        raise SystemExit(f"Novel not found: {NEXT_TITLE!r}")

    db.set_novel_status(skip.id, "abandoned")
    db.delete_novel_data(skip.id)

    for novel in db.list_novels():
        if novel.status == "active" and novel.id != nxt.id:
            db.set_novel_status(novel.id, "queued")

    db.set_novel_status(nxt.id, "active")

    if db.episode_count_for_novel(nxt.id) == 0:
        max_eps = getattr(config, "max_episodes", 12)
        ep_count = nxt.estimated_episodes or estimate_episode_count(
            nxt.chapter_count, max_episodes=max_eps
        )
        ep_count = min(ep_count, max_eps)
        db.set_estimated_episodes(nxt.id, ep_count)
        for i, (start, end) in enumerate(chapter_ranges(nxt.chapter_count, ep_count), start=1):
            beat = f"Episode {i}: chapters {start}-{end}."
            db.add_episode(
                novel_id=nxt.id,
                episode_num=i,
                chapter_start=start,
                chapter_end=end,
                plot_beat_summary=beat,
                cumulative_synopsis=beat,
                status="pending",
            )

    reset_checkpoint_for_novel(config.path("data_dir"), nxt.id, nxt.title)

    skip_row = db.get_novel(skip.id)
    active = db.get_active_novel()
    print(f"abandoned: [{skip_row.id}] {skip_row.title} -> {skip_row.status}")
    print(f"active:    [{active.id}] {active.title} by {active.author}")
    print(f"episodes:  {db.episode_count_for_novel(active.id)} for {active.title}")


if __name__ == "__main__":
    main()
