"""Rahasya.exe content pipeline CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.book_queue.discovery import NovelDiscovery
from src.book_queue.queue import BookQueue
from src.book_queue.store import Database
from src.config import load_config
from src.pipeline.logger import PipelineLogger
from src.pipeline.orchestrator import Pipeline
from src.review.telegram import TelegramBot


def cmd_run(_: argparse.Namespace) -> None:
    pipeline = Pipeline(load_config())
    bundle_id = pipeline.run()
    print(f"Pipeline complete. Bundle: {bundle_id}")


def cmd_status(_: argparse.Namespace) -> None:
    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    queue = BookQueue(config, logger)
    summary = queue.status_summary()
    active = summary["active"]
    if active:
        print(f"Active: {active.title} by {active.author}")
        print(f"  Episode: {active.current_episode}/{active.estimated_episodes}")
        print(f"  Status: {active.status}")
    else:
        print("No active novel")
    print(f"Queued: {summary['queued_count']}")
    print(f"Completed: {summary['completed_count']}")
    print(f"Pending reviews: {summary['pending_reviews']}")


def cmd_queue(_: argparse.Namespace) -> None:
    config = load_config()
    db = Database(config.path("db_path"))
    for status in ("active", "queued", "completed"):
        novels = db.list_novels(status)
        if novels:
            print(f"\n=== {status.upper()} ===")
            for n in novels:
                print(f"  [{n.id}] {n.title} by {n.author} ({n.status})")


def cmd_discover(_: argparse.Namespace) -> None:
    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    db = Database(config.path("db_path"))
    discovery = NovelDiscovery(config, db, logger)
    added = discovery.run()
    print(f"Discovery complete. Added {added} novels.")


def cmd_add_novel(args: argparse.Namespace) -> None:
    config = load_config()
    db = Database(config.path("db_path"))
    novel_id = db.add_novel(
        title=args.title,
        author=args.author,
        country=args.country or "",
        chapter_count=args.chapters or 20,
        public_domain=True,
        status="queued",
    )
    print(f"Added novel id={novel_id}: {args.title} by {args.author}")


def cmd_approve(args: argparse.Namespace) -> None:
    pipeline = Pipeline(load_config())
    pipeline.approve_and_post(args.bundle_id)
    print(f"Approved and queued: {args.bundle_id}")


def cmd_reject(args: argparse.Namespace) -> None:
    pipeline = Pipeline(load_config())
    pipeline.reject_bundle(args.bundle_id, args.reason or "")
    print(f"Rejected: {args.bundle_id}")


def cmd_bot(_: argparse.Namespace) -> None:
    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    pipeline = Pipeline(config)

    def on_approve(bundle_id: str) -> None:
        pipeline.approve_and_post(bundle_id)

    def on_reject(bundle_id: str, reason: str) -> None:
        pipeline.reject_bundle(bundle_id, reason)

    bot = TelegramBot(config, logger, on_approve, on_reject)
    bot.poll()


def cmd_retry(_: argparse.Namespace) -> None:
    """Re-run pipeline for the next pending episode."""
    pipeline = Pipeline(load_config())
    bundle_id = pipeline.run()
    print(f"Retry complete. Bundle: {bundle_id}")


def cmd_telegram_id(_: argparse.Namespace) -> None:
    """Fetch your TELEGRAM_CHAT_ID from recent messages to your bot."""
    import requests

    config = load_config()
    token = config.telegram_bot_token
    if not token:
        print("TELEGRAM_BOT_TOKEN is missing in .env")
        sys.exit(1)

    print("1. Open Telegram and send any message to YOUR bot (e.g. hi)")
    print("2. This command reads that message and prints your chat ID\n")

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        updates = resp.json().get("result", [])
    except requests.RequestException as exc:
        print(f"Failed to contact Telegram: {exc}")
        sys.exit(1)

    if not updates:
        print("No messages found yet.")
        print("Send 'hi' to your bot in Telegram, then run this command again.")
        sys.exit(1)

    seen: set[int] = set()
    for update in reversed(updates):
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        if chat_id in seen:
            continue
        seen.add(chat_id)
        name = chat.get("first_name", "")
        username = chat.get("username", "")
        print(f"TELEGRAM_CHAT_ID={chat_id}  ({name} @{username})".strip())

    print("\nCopy the number into .env as TELEGRAM_CHAT_ID=")


def cmd_meta_test(_: argparse.Namespace) -> None:
    """Verify Meta/Instagram API credentials."""
    from src.scheduler.meta import MetaScheduler

    config = load_config()
    result = MetaScheduler.verify_connection(config)
    if result["ok"]:
        acct = result["account"]
        print("✅ Meta connection OK")
        print(f"  Instagram: @{acct.get('username', '?')} ({acct.get('name', '')})")
        print(f"  IG User ID: {acct.get('id')}")
    else:
        print(f"❌ Meta connection failed: {result['error']}")
        print("\nRequired .env vars:")
        print("  META_ACCESS_TOKEN  — long-lived page/user token with instagram_content_publish")
        print("  META_IG_USER_ID    — Instagram Business account ID")
        print("  META_PAGE_ID       — Facebook Page ID (for cover image upload)")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rahasya.exe content pipeline")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Generate today's content").set_defaults(func=cmd_run)
    sub.add_parser("status", help="Show pipeline status").set_defaults(func=cmd_status)
    sub.add_parser("queue", help="Show novel queue").set_defaults(func=cmd_queue)
    sub.add_parser("discover", help="Run novel discovery").set_defaults(func=cmd_discover)
    sub.add_parser("bot", help="Start Telegram approval bot").set_defaults(func=cmd_bot)
    sub.add_parser(
        "telegram-id",
        help="Get your TELEGRAM_CHAT_ID after messaging your bot",
    ).set_defaults(func=cmd_telegram_id)

    sub.add_parser("retry", help="Re-run pipeline").set_defaults(func=cmd_retry)
    sub.add_parser("meta-test", help="Verify Meta/Instagram API connection").set_defaults(func=cmd_meta_test)

    add_parser = sub.add_parser("add-novel", help="Manually add a novel")
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--author", required=True)
    add_parser.add_argument("--country", default="")
    add_parser.add_argument("--chapters", type=int, default=20)
    add_parser.set_defaults(func=cmd_add_novel)

    approve_parser = sub.add_parser("approve", help="Approve a review bundle")
    approve_parser.add_argument("bundle_id")
    approve_parser.set_defaults(func=cmd_approve)

    reject_parser = sub.add_parser("reject", help="Reject a review bundle")
    reject_parser.add_argument("bundle_id")
    reject_parser.add_argument("--reason", default="")
    reject_parser.set_defaults(func=cmd_reject)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
