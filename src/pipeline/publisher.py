"""Lightweight Instagram publish path — no LLM / generation dependencies."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.book_queue.store import Database
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.review.bundle import ReviewBundleWriter
from src.review.telegram import TelegramNotifier
from src.scheduler.factory import get_scheduler


def approve_and_post(
    config: AppConfig, bundle_id: str, logger: PipelineLogger | None = None
) -> str | None:
    """Approve a review bundle and upload reel + carousel to Instagram."""
    logger = logger or PipelineLogger(config.path("logs_dir"))
    db = Database(config.path("db_path"))
    review = ReviewBundleWriter(config, db)
    telegram = TelegramNotifier(config, logger)
    scheduler = get_scheduler(config, logger)

    logger.start("approve", bundle_id)
    approved_dir = review.approve(bundle_id)
    caption_path = approved_dir / "caption.txt"
    caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else ""

    post_details = None
    post_details_path = approved_dir / "post_details.json"
    if post_details_path.exists():
        from src.script_gen.post_details import PostDetails

        data = json.loads(post_details_path.read_text(encoding="utf-8"))
        post_details = PostDetails(**data)

    thumbnail_path = approved_dir / "thumbnail.png"
    if not thumbnail_path.exists():
        thumbnail_path = None

    post_id = scheduler.queue_posts(
        approved_dir / "reel.mp4",
        sorted(approved_dir.glob("static_post_*.png")) or [approved_dir / "static_post.png"],
        caption,
        bundle_id,
        thumbnail_path=thumbnail_path,
        post_details=post_details,
    )

    if post_id.startswith("manual_package:"):
        msg = (
            f"Instagram API upload failed — saved for manual upload: {post_id}. "
            "Bundle stays in pending_publish; upload from output/ready_to_upload/ manually."
        )
        logger.fail("approve", msg)
        telegram.send_error(msg)
        return None

    carousel_failed = "carousel_failed:" in post_id
    reel_posted = "reel_pub:" in post_id
    if not reel_posted:
        msg = f"Instagram publish returned without reel_pub id: {post_id}"
        logger.fail("approve", msg)
        telegram.send_error(msg)
        return None

    bundle = db.get_review_bundle(bundle_id)
    if bundle:
        db.log_post(
            bundle["novel_id"],
            bundle["episode_num"],
            bundle_id,
            "posted",
            metricool_id=post_id,
        )
        db.set_review_status(bundle_id, "posted")
        db.set_episode_status_by_num(bundle["novel_id"], bundle["episode_num"], "generated")
        db.refresh_novel_current_episode(bundle["novel_id"])

    posted_dir = config.path("output_dir") / "posted" / bundle_id
    posted_dir.parent.mkdir(parents=True, exist_ok=True)
    if posted_dir.exists():
        shutil.rmtree(posted_dir)
    shutil.copytree(approved_dir, posted_dir)

    provider = config.post_provider or "meta"
    if carousel_failed:
        reason = post_id.split("carousel_failed:", 1)[-1].split(";", 1)[0]
        telegram.send_info(
            f"✅ Reel posted: `{bundle_id}`\n"
            f"⚠️ Carousel failed ({reason}) — slides saved to "
            f"`output/ready_to_upload/{bundle_id}/` for manual upload.\n"
            f"{provider}: {post_id}"
        )
        logger.warn("approve", f"partial publish — reel ok, carousel failed ({reason})")
    else:
        telegram.send_info(f"✅ Posted/queued: `{bundle_id}`\n{provider}: {post_id}")
    logger.ok("approve", post_id)
    return post_id


def publish_pending(config: AppConfig, logger: PipelineLogger | None = None) -> str | None:
    """Post the oldest bundle queued with pending_publish (after min delay)."""
    logger = logger or PipelineLogger(config.path("logs_dir"))
    db = Database(config.path("db_path"))

    bundles = db.list_pending_publish()
    if not bundles:
        logger.info("publish | no bundles waiting")
        return None

    min_age = timedelta(hours=config.min_publish_delay_hours)
    now = datetime.now(ZoneInfo(config.timezone))
    eligible: list[dict] = []
    for bundle in bundles:
        created_raw = bundle.get("metadata", {}).get("created_at", "")
        try:
            created = datetime.fromisoformat(created_raw)
            if created.tzinfo is None:
                created = created.replace(tzinfo=ZoneInfo(config.timezone))
        except ValueError:
            created = now - min_age
        if now - created >= min_age:
            eligible.append(bundle)

    if not eligible:
        logger.info(
            f"publish | waiting — next bundle needs "
            f"{config.min_publish_delay_hours}h after generation"
        )
        return None

    bundle_id = eligible[0]["bundle_id"]
    logger.start("publish", bundle_id)
    post_id = approve_and_post(config, bundle_id, logger=logger)
    if not post_id:
        return None
    return bundle_id


def pending_publish_count(config: AppConfig) -> int:
    db = Database(config.path("db_path"))
    return len(db.list_pending_publish())
