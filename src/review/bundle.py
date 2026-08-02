"""Review bundle writer."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from src.script_gen.export import write_script_txt, write_transcript_txt
from src.script_gen.post_details import build_post_details, write_post_details_json, write_post_details_txt
from src.book_queue.models import EpisodeContext, ScriptOutput
from src.book_queue.store import Database
from src.config import AppConfig


class ReviewBundleWriter:
    def __init__(self, config: AppConfig, db: Database) -> None:
        self.config = config
        self.db = db

    def create_bundle_id(self, context: EpisodeContext) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        slug = self._slugify(context.novel.title)
        return f"{date_str}_{slug}_ep{context.episode.episode_num}"

    def write(
        self,
        context: EpisodeContext,
        script: ScriptOutput,
        caption: str,
        voiceover_path: Path,
        reel_path: Path,
        static_paths: list[Path] | Path,
        thumbnail_path: Path | None = None,
        script_txt_path: Path | None = None,
        transcript_path: Path | None = None,
        post_details_txt_path: Path | None = None,
        post_details_json_path: Path | None = None,
    ) -> tuple[str, Path]:
        if isinstance(static_paths, Path):
            static_paths = [static_paths]

        bundle_id = self.create_bundle_id(context)
        bundle_dir = self.config.path("output_dir") / "review" / bundle_id
        bundle_dir.mkdir(parents=True, exist_ok=True)

        metadata: dict[str, Any] = {
            "bundle_id": bundle_id,
            "novel_title": context.novel.title,
            "novel_author": context.novel.author,
            "episode_num": context.episode.episode_num,
            "total_episodes": context.total_episodes,
            "script": script.__dict__,
            "caption": caption,
            "static_post_count": len(static_paths),
            "static_posts": [p.name for p in static_paths],
            "transcript": script.episode_script(),
            "status": "pending_review",
            "created_at": datetime.now().isoformat(),
        }

        (bundle_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (bundle_dir / "caption.txt").write_text(caption, encoding="utf-8")

        self._copy_or_link(voiceover_path, bundle_dir / "voiceover.mp3")
        self._copy_or_link(reel_path, bundle_dir / "reel.mp4")

        for i, static_path in enumerate(static_paths):
            self._copy_or_link(static_path, bundle_dir / f"static_post_{i + 1:02d}.png")
        if static_paths:
            self._copy_or_link(static_paths[0], bundle_dir / "static_post.png")

        if thumbnail_path and thumbnail_path.exists():
            self._copy_or_link(thumbnail_path, bundle_dir / "thumbnail.png")

        if script_txt_path and script_txt_path.exists():
            self._copy_or_link(script_txt_path, bundle_dir / "script.txt")
        else:
            write_script_txt(context, script, bundle_dir / "script.txt", caption=caption)

        if transcript_path and transcript_path.exists():
            self._copy_or_link(transcript_path, bundle_dir / "transcript.txt")
        else:
            write_transcript_txt(script.episode_script(), bundle_dir / "transcript.txt")

        post_details = build_post_details(
            context, script, self.config, caption, static_slide_count=len(static_paths)
        )
        if post_details_txt_path and post_details_txt_path.exists():
            self._copy_or_link(post_details_txt_path, bundle_dir / "post_details.txt")
        else:
            write_post_details_txt(post_details, bundle_dir / "post_details.txt")
        if post_details_json_path and post_details_json_path.exists():
            self._copy_or_link(post_details_json_path, bundle_dir / "post_details.json")
        else:
            write_post_details_json(post_details, bundle_dir / "post_details.json")

        self.db.add_review_bundle(
            bundle_id=bundle_id,
            novel_id=context.novel.id,
            episode_num=context.episode.episode_num,
            bundle_path=str(bundle_dir),
            metadata=metadata,
            status="pending_review",
        )
        return bundle_id, bundle_dir

    def approve(self, bundle_id: str) -> Path:
        bundle = self.db.get_review_bundle(bundle_id)
        if not bundle:
            raise ValueError(f"Bundle not found: {bundle_id}")

        src = Path(bundle["bundle_path"])
        approved_dir = self.config.path("output_dir") / "approved" / bundle_id
        approved_dir.parent.mkdir(parents=True, exist_ok=True)

        if src.exists():
            if approved_dir.exists():
                shutil.rmtree(approved_dir)
            shutil.copytree(src, approved_dir)

        self.db.set_review_status(bundle_id, "approved")
        return approved_dir

    def reject(self, bundle_id: str, reason: str = "") -> None:
        self.db.set_review_status(bundle_id, "rejected")
        bundle = self.db.get_review_bundle(bundle_id)
        if bundle:
            meta_path = Path(bundle["bundle_path"]) / "metadata.json"
            if meta_path.exists():
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                data["status"] = "rejected"
                data["reject_reason"] = reason
                meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _copy_or_link(self, src: Path, dst: Path) -> None:
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)

    def _slugify(self, text: str) -> str:
        import re
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return slug[:40] or "novel"
