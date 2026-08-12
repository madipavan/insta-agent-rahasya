"""SQLite persistence for novels, episodes, and logs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.book_queue.models import Episode, Novel
from src.book_queue.slug import slugify_novel
from src.book_queue.pacing import estimate_episode_count

# LLM arcs sometimes nest planned_hook / beat fields as objects; sqlite3 rejects dict/list.
_TEXT_KEYS = (
    "text",
    "hook",
    "line",
    "caption",
    "value",
    "summary",
    "content",
    "angle",
    "cliffhanger",
    "plot_beat_summary",
    "cumulative_synopsis",
    "planned_hook",
    "planned_cliffhanger",
    "retention_angle",
)


def _as_sqlite_text(value: Any) -> str:
    """Coerce LLM/nested values to a sqlite3-bindable TEXT string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in _TEXT_KEYS:
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        parts = [_as_sqlite_text(item) for item in value]
        parts = [p for p in parts if p]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        return json.dumps(parts, ensure_ascii=False)
    if isinstance(value, (bool, int, float)):
        return str(value)
    return str(value)


def _as_sqlite_json_text(value: Any) -> str:
    """Coerce script/JSON payloads; never peel nested keys into a bare string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS novels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    country TEXT DEFAULT '',
                    chapter_count INTEGER DEFAULT 20,
                    public_domain INTEGER DEFAULT 1,
                    source_link TEXT DEFAULT '',
                    adaptation_checked INTEGER DEFAULT 0,
                    estimated_episodes INTEGER DEFAULT 12,
                    status TEXT DEFAULT 'queued',
                    current_episode INTEGER DEFAULT 0,
                    bgm_path TEXT DEFAULT '',
                    thumbnail_base_path TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    novel_id INTEGER NOT NULL,
                    episode_num INTEGER NOT NULL,
                    chapter_start INTEGER NOT NULL,
                    chapter_end INTEGER NOT NULL,
                    plot_beat_summary TEXT DEFAULT '',
                    cumulative_synopsis TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (novel_id) REFERENCES novels(id)
                );

                CREATE TABLE IF NOT EXISTS post_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    novel_id INTEGER,
                    episode_num INTEGER,
                    bundle_id TEXT,
                    status TEXT,
                    metricool_id TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS discovery_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    author TEXT,
                    result TEXT,
                    reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS review_bundles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bundle_id TEXT UNIQUE NOT NULL,
                    novel_id INTEGER,
                    episode_num INTEGER,
                    bundle_path TEXT,
                    status TEXT DEFAULT 'pending_review',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(novels)").fetchall()}
        if "bgm_path" not in cols:
            conn.execute("ALTER TABLE novels ADD COLUMN bgm_path TEXT DEFAULT ''")
        if "thumbnail_base_path" not in cols:
            conn.execute("ALTER TABLE novels ADD COLUMN thumbnail_base_path TEXT DEFAULT ''")

        ep_cols = {row[1] for row in conn.execute("PRAGMA table_info(episodes)").fetchall()}
        for col in ("planned_hook", "planned_cliffhanger", "retention_angle", "script_json"):
            if col not in ep_cols:
                conn.execute(f"ALTER TABLE episodes ADD COLUMN {col} TEXT DEFAULT ''")

        novel_cols = {row[1] for row in conn.execute("PRAGMA table_info(novels)").fetchall()}
        for col in ("novel_logline", "story_summary", "retention_strategy", "pdf_path"):
            if col not in novel_cols:
                conn.execute(f"ALTER TABLE novels ADD COLUMN {col} TEXT DEFAULT ''")

    def _row_to_novel(self, row: sqlite3.Row) -> Novel:
        keys = row.keys()
        return Novel(
            id=row["id"],
            title=row["title"],
            author=row["author"],
            country=row["country"] or "",
            chapter_count=row["chapter_count"],
            public_domain=bool(row["public_domain"]),
            source_link=row["source_link"] or "",
            adaptation_checked=bool(row["adaptation_checked"]),
            estimated_episodes=row["estimated_episodes"],
            status=row["status"],
            current_episode=row["current_episode"],
            novel_logline=row["novel_logline"] if "novel_logline" in keys else "",
            story_summary=row["story_summary"] if "story_summary" in keys else "",
            retention_strategy=row["retention_strategy"] if "retention_strategy" in keys else "",
            pdf_path=row["pdf_path"] if "pdf_path" in keys else "",
        )

    def _row_to_episode(self, row: sqlite3.Row) -> Episode:
        keys = row.keys()
        return Episode(
            id=row["id"],
            novel_id=row["novel_id"],
            episode_num=row["episode_num"],
            chapter_start=row["chapter_start"],
            chapter_end=row["chapter_end"],
            plot_beat_summary=row["plot_beat_summary"] or "",
            cumulative_synopsis=row["cumulative_synopsis"] or "",
            status=row["status"] or "pending",
            planned_hook=row["planned_hook"] if "planned_hook" in keys else "",
            planned_cliffhanger=row["planned_cliffhanger"] if "planned_cliffhanger" in keys else "",
            retention_angle=row["retention_angle"] if "retention_angle" in keys else "",
            script_json=row["script_json"] if "script_json" in keys else "",
        )

    def add_novel(
        self,
        title: str,
        author: str,
        country: str = "",
        chapter_count: int = 20,
        public_domain: bool = True,
        source_link: str = "",
        adaptation_checked: bool = False,
        status: str = "queued",
        max_episodes: int = 12,
    ) -> int:
        episodes = estimate_episode_count(chapter_count, max_episodes=max_episodes)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO novels (title, author, country, chapter_count, public_domain,
                    source_link, adaptation_checked, estimated_episodes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    author,
                    country,
                    chapter_count,
                    int(public_domain),
                    source_link,
                    int(adaptation_checked),
                    episodes,
                    status,
                ),
            )
            return cur.lastrowid

    def get_novel(self, novel_id: int) -> Optional[Novel]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM novels WHERE id = ?", (novel_id,)).fetchone()
            return self._row_to_novel(row) if row else None

    def get_active_novel(self) -> Optional[Novel]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM novels WHERE status = 'active' ORDER BY id LIMIT 1"
            ).fetchone()
            return self._row_to_novel(row) if row else None

    def set_novel_status(self, novel_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE novels SET status = ? WHERE id = ?", (status, novel_id))

    def set_estimated_episodes(self, novel_id: int, estimated_episodes: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE novels SET estimated_episodes = ? WHERE id = ?",
                (estimated_episodes, novel_id),
            )

    def increment_episode(self, novel_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE novels SET current_episode = current_episode + 1 WHERE id = ?",
                (novel_id,),
            )

    def count_queued_novels(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM novels WHERE status = 'queued'"
            ).fetchone()
            return row["c"]

    def get_next_queued_novel(self) -> Optional[Novel]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM novels WHERE status = 'queued' ORDER BY id LIMIT 1"
            ).fetchone()
            return self._row_to_novel(row) if row else None

    def list_novels(self, status: Optional[str] = None) -> list[Novel]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM novels WHERE status = ? ORDER BY id", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM novels ORDER BY id").fetchall()
            return [self._row_to_novel(r) for r in rows]

    def novel_exists(self, title: str, author: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM novels WHERE title = ? AND author = ?",
                (title, author),
            ).fetchone()
            return row is not None

    def add_episode(
        self,
        novel_id: int,
        episode_num: int,
        chapter_start: int,
        chapter_end: int,
        plot_beat_summary: str = "",
        cumulative_synopsis: str = "",
        status: str = "pending",
        planned_hook: str = "",
        planned_cliffhanger: str = "",
        retention_angle: str = "",
        script_json: str = "",
    ) -> int:
        # Parameter 8 is planned_hook — LLMs often return dicts here.
        plot_beat_summary = _as_sqlite_text(plot_beat_summary)
        cumulative_synopsis = _as_sqlite_text(cumulative_synopsis)
        status = _as_sqlite_text(status) or "pending"
        planned_hook = _as_sqlite_text(planned_hook)
        planned_cliffhanger = _as_sqlite_text(planned_cliffhanger)
        retention_angle = _as_sqlite_text(retention_angle)
        script_json = _as_sqlite_json_text(script_json)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO episodes (novel_id, episode_num, chapter_start, chapter_end,
                    plot_beat_summary, cumulative_synopsis, status,
                    planned_hook, planned_cliffhanger, retention_angle, script_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    novel_id,
                    episode_num,
                    chapter_start,
                    chapter_end,
                    plot_beat_summary,
                    cumulative_synopsis,
                    status,
                    planned_hook,
                    planned_cliffhanger,
                    retention_angle,
                    script_json,
                ),
            )
            return cur.lastrowid

    def get_episode(self, novel_id: int, episode_num: int) -> Optional[Episode]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM episodes WHERE novel_id = ? AND episode_num = ?",
                (novel_id, episode_num),
            ).fetchone()
            return self._row_to_episode(row) if row else None

    def get_next_pending_episode(self, novel_id: int) -> Optional[Episode]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM episodes WHERE novel_id = ? AND status = 'pending'
                ORDER BY episode_num LIMIT 1
                """,
                (novel_id,),
            ).fetchone()
            return self._row_to_episode(row) if row else None

    def update_episode(
        self,
        episode_id: int,
        plot_beat_summary: str,
        cumulative_synopsis: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE episodes SET plot_beat_summary = ?, cumulative_synopsis = ?
                WHERE id = ?
                """,
                (
                    _as_sqlite_text(plot_beat_summary),
                    _as_sqlite_text(cumulative_synopsis),
                    episode_id,
                ),
            )

    def set_episode_status(self, episode_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE episodes SET status = ? WHERE id = ?", (status, episode_id))

    def set_episode_status_by_num(self, novel_id: int, episode_num: int, status: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE episodes SET status = ?
                WHERE novel_id = ? AND episode_num = ?
                """,
                (status, novel_id, episode_num),
            )
            return cur.rowcount > 0

    def reconcile_episodes_to_checkpoint(
        self, novel_id: int, completed_episodes: list[int]
    ) -> int:
        """Align episode rows and post_log with checkpoint.json (fixes stale CI state)."""
        if not completed_episodes:
            return 0

        completed = sorted({int(ep) for ep in completed_episodes})
        max_ep = max(completed)
        placeholders = ",".join("?" * len(completed))
        applied = 0

        with self._connect() as conn:
            for ep_num in completed:
                cur = conn.execute(
                    """
                    UPDATE episodes SET status = 'generated'
                    WHERE novel_id = ? AND episode_num = ?
                    """,
                    (novel_id, ep_num),
                )
                applied += cur.rowcount

            conn.execute(
                f"""
                UPDATE episodes SET status = 'pending'
                WHERE novel_id = ? AND episode_num NOT IN ({placeholders})
                """,
                (novel_id, *completed),
            )
            conn.execute(
                f"""
                DELETE FROM post_log
                WHERE novel_id = ? AND episode_num NOT IN ({placeholders})
                """,
                (novel_id, *completed),
            )
            conn.execute(
                "UPDATE novels SET current_episode = ? WHERE id = ?",
                (max_ep, novel_id),
            )

        return applied

    def refresh_novel_current_episode(self, novel_id: int) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT MAX(episode_num) AS max_ep FROM episodes
                WHERE novel_id = ? AND status = 'generated'
                """,
                (novel_id,),
            ).fetchone()
            if row and row["max_ep"] is not None:
                conn.execute(
                    """
                    UPDATE novels SET current_episode = ?
                    WHERE id = ? AND current_episode < ?
                    """,
                    (row["max_ep"], novel_id, row["max_ep"]),
                )

    def sync_episode_progress(self, novel_id: int, output_dir: Path | None = None) -> int:
        """Align episode rows with generated/posted bundles (fixes cache/DB drift)."""
        novel = self.get_novel(novel_id)
        if not novel:
            return 0

        done_eps: set[int] = set()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT episode_num FROM review_bundles
                WHERE novel_id = ? AND status IN (
                    'posted', 'pending_publish', 'approved', 'pending_review'
                )
                """,
                (novel_id,),
            ).fetchall()
            done_eps.update(r["episode_num"] for r in rows if r["episode_num"])

            rows = conn.execute(
                """
                SELECT DISTINCT episode_num FROM post_log
                WHERE novel_id = ? AND status IN ('posted', 'generated')
                """,
                (novel_id,),
            ).fetchall()
            done_eps.update(r["episode_num"] for r in rows if r["episode_num"])

            rows = conn.execute(
                """
                SELECT DISTINCT episode_num FROM episodes
                WHERE novel_id = ? AND status = 'generated'
                """,
                (novel_id,),
            ).fetchall()
            done_eps.update(r["episode_num"] for r in rows if r["episode_num"])

        if output_dir is not None:
            done_eps.update(self._episode_nums_from_output_folders(novel, output_dir))

        synced = 0
        for ep_num in sorted(done_eps):
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE episodes SET status = 'generated'
                    WHERE novel_id = ? AND episode_num = ? AND status = 'pending'
                    """,
                    (novel_id, ep_num),
                )
                synced += cur.rowcount

        if synced or done_eps:
            self.refresh_novel_current_episode(novel_id)
        return synced

    def episode_output_exists(self, novel: Novel, episode_num: int, output_dir: Path) -> bool:
        return episode_num in self._episode_nums_from_output_folders(novel, output_dir)

    def log_episode_state(self, novel_id: int, logger) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT episode_num, status FROM episodes
                WHERE novel_id = ? ORDER BY episode_num
                """,
                (novel_id,),
            ).fetchall()
        if not rows:
            logger.info("queue | no episodes in DB for active novel")
            return
        summary = ", ".join(f"ep{r['episode_num']}:{r['status']}" for r in rows[:8])
        if len(rows) > 8:
            summary += f", ... (+{len(rows) - 8} more)"
        logger.info(f"queue | episode DB state — {summary}")

    def _episode_nums_from_output_folders(self, novel: Novel, output_dir: Path) -> set[int]:
        import re

        slug = slugify_novel(novel.title)
        nums: set[int] = set()
        # Only finished bundles — ignore output/work (failed partial CI runs).
        for sub in ("posted", "approved", "ready_to_upload", "review"):
            folder = output_dir / sub
            if not folder.exists():
                continue
            for child in folder.iterdir():
                if not child.is_dir():
                    continue
                name = child.name.lower()
                if slug not in name:
                    continue
                match = re.search(r"_ep(\d+)$", child.name, re.IGNORECASE)
                if match and (child / "reel.mp4").exists():
                    nums.add(int(match.group(1)))
        return nums

    def episode_count_for_novel(self, novel_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM episodes WHERE novel_id = ?", (novel_id,)
            ).fetchone()
            return row["c"]

    def log_post(
        self,
        novel_id: int,
        episode_num: int,
        bundle_id: str,
        status: str,
        metricool_id: str = "",
        error: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO post_log (novel_id, episode_num, bundle_id, status, metricool_id, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (novel_id, episode_num, bundle_id, status, metricool_id, error),
            )

    def log_discovery(self, title: str, author: str, result: str, reason: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO discovery_log (title, author, result, reason) VALUES (?, ?, ?, ?)",
                (title, author, result, reason),
            )

    def add_review_bundle(
        self,
        bundle_id: str,
        novel_id: int,
        episode_num: int,
        bundle_path: str,
        metadata: dict[str, Any],
        status: str = "pending_review",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO review_bundles
                (bundle_id, novel_id, episode_num, bundle_path, status, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle_id,
                    novel_id,
                    episode_num,
                    bundle_path,
                    status,
                    json.dumps(metadata),
                ),
            )

    def get_review_bundle(self, bundle_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_bundles WHERE bundle_id = ?", (bundle_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "bundle_id": row["bundle_id"],
                "novel_id": row["novel_id"],
                "episode_num": row["episode_num"],
                "bundle_path": row["bundle_path"],
                "status": row["status"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }

    def set_review_status(self, bundle_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE review_bundles SET status = ? WHERE bundle_id = ?",
                (status, bundle_id),
            )

    def list_pending_reviews(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM review_bundles WHERE status = 'pending_review' ORDER BY id"
            ).fetchall()
            return [
                {
                    "bundle_id": r["bundle_id"],
                    "novel_id": r["novel_id"],
                    "episode_num": r["episode_num"],
                    "bundle_path": r["bundle_path"],
                    "status": r["status"],
                    "metadata": json.loads(r["metadata_json"] or "{}"),
                }
                for r in rows
            ]

    def list_pending_publish(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM review_bundles WHERE status = 'pending_publish' ORDER BY id"
            ).fetchall()
            return [
                {
                    "bundle_id": r["bundle_id"],
                    "novel_id": r["novel_id"],
                    "episode_num": r["episode_num"],
                    "bundle_path": r["bundle_path"],
                    "status": r["status"],
                    "metadata": json.loads(r["metadata_json"] or "{}"),
                }
                for r in rows
            ]

    def set_novel_story_bible(
        self,
        novel_id: int,
        novel_logline: str,
        story_summary: str,
        retention_strategy: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE novels SET novel_logline = ?, story_summary = ?, retention_strategy = ?
                WHERE id = ?
                """,
                (
                    _as_sqlite_text(novel_logline),
                    _as_sqlite_text(story_summary),
                    _as_sqlite_text(retention_strategy),
                    novel_id,
                ),
            )

    def set_novel_pdf_path(self, novel_id: int, pdf_path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE novels SET pdf_path = ? WHERE id = ?",
                (pdf_path, novel_id),
            )

    def set_episode_script_json(self, episode_id: int, script_json: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE episodes SET script_json = ? WHERE id = ?",
                (_as_sqlite_json_text(script_json), episode_id),
            )

    def get_episode_script_json(self, novel_id: int, episode_num: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT script_json FROM episodes
                WHERE novel_id = ? AND episode_num = ?
                """,
                (novel_id, episode_num),
            ).fetchone()
            if not row:
                return ""
            keys = row.keys()
            return (row["script_json"] if "script_json" in keys else "") or ""

    def delete_novel_data(self, novel_id: int) -> None:
        """Remove episode rows, review bundles, and post log for a novel."""
        with self._connect() as conn:
            conn.execute("DELETE FROM episodes WHERE novel_id = ?", (novel_id,))
            conn.execute("DELETE FROM review_bundles WHERE novel_id = ?", (novel_id,))
            conn.execute("DELETE FROM post_log WHERE novel_id = ?", (novel_id,))

    def set_novel_assets(self, novel_id: int, bgm_path: str, thumbnail_base_path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE novels SET bgm_path = ?, thumbnail_base_path = ? WHERE id = ?",
                (bgm_path, thumbnail_base_path, novel_id),
            )

    def get_novel_bgm_path(self, novel_id: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT bgm_path FROM novels WHERE id = ?", (novel_id,)
            ).fetchone()
            return row["bgm_path"] if row and row["bgm_path"] else ""

    def get_novel_thumbnail_base(self, novel_id: int) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT thumbnail_base_path FROM novels WHERE id = ?", (novel_id,)
            ).fetchone()
            return row["thumbnail_base_path"] if row and row["thumbnail_base_path"] else ""

    def get_previous_episode_context(self, novel_id: int, episode_num: int) -> dict | None:
        """Load script metadata from the previous episode for recap continuity."""
        if episode_num <= 1:
            return None
        prev_num = episode_num - 1
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT metadata_json FROM review_bundles
                WHERE novel_id = ? AND episode_num = ?
                ORDER BY id DESC LIMIT 1
                """,
                (novel_id, prev_num),
            ).fetchone()
        if not row:
            episode = self.get_episode(novel_id, prev_num)
            if episode:
                return {
                    "summary": episode.plot_beat_summary,
                    "voiceover_excerpt": episode.plot_beat_summary,
                    "cliffhanger": "",
                }
            return None

        metadata = json.loads(row["metadata_json"] or "{}")
        script = metadata.get("script", {})
        episode_only = script.get("episode_only_script", "")
        voiceover = script.get("voiceover_script", "")
        recap = script.get("recap_opener", "")
        if not episode_only and voiceover:
            episode_only = voiceover.replace(recap, "", 1).strip() if recap else voiceover
        excerpt = episode_only[:400] + "..." if len(episode_only) > 400 else episode_only
        return {
            "summary": script.get("caption_teaser") or episode_only[:300],
            "voiceover_excerpt": excerpt,
            "cliffhanger": script.get("cliffhanger", ""),
        }

    def import_seed_file(self, seed_path: Path) -> int:
        if not seed_path.exists():
            return 0
        with open(seed_path, encoding="utf-8") as f:
            data = json.load(f)
        count = 0
        for item in data.get("novels", []):
            title = item.get("title", "")
            author = item.get("author", "")
            if not title or not author or self.novel_exists(title, author):
                continue
            self.add_novel(
                title=title,
                author=author,
                country=item.get("country", ""),
                chapter_count=item.get("chapter_count", 20),
                public_domain=item.get("public_domain", True),
                source_link=item.get("source_link", ""),
                adaptation_checked=item.get("adaptation_checked", False),
                status="queued",
            )
            count += 1
        return count
