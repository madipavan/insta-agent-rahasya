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


def cmd_publish(args: argparse.Namespace) -> None:
    """Publish the oldest queued bundle to Meta (run at post_time)."""
    config = load_config()
    if getattr(args, "now", False):
        config.min_publish_delay_hours = 0
    from src.pipeline.publisher import publish_pending

    bundle_id = publish_pending(config)
    if bundle_id:
        print(f"Published: {bundle_id}")
    else:
        if getattr(args, "now", False):
            print("Publish failed or nothing in pending_publish queue.")
            sys.exit(1)
        print("Nothing to publish yet (waiting for min_publish_delay_hours).")


def cmd_run(args: argparse.Namespace) -> None:
    config = load_config()
    pipeline = Pipeline(config)
    if getattr(args, "next_novel", False):
        active = pipeline.queue.db.get_active_novel()
        if active:
            clean = not getattr(args, "keep_output", False)
            novel = pipeline.queue.skip_to_next_novel(clean_output=clean)
            print(f"Skipped novel: {active.title}")
            print(f"Now active: {novel.title} by {novel.author}")
        else:
            print("No active novel to skip — continuing with queue.")
    bundle_id = pipeline.run(regen_script=bool(getattr(args, "regen_script", False)))
    if getattr(args, "publish_now", False):
        config.min_publish_delay_hours = 0
        published = pipeline.publish_pending()
        if published:
            print(f"Published: {published}")
        else:
            print("Generate succeeded but publish failed or nothing to publish.")
            sys.exit(1)
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
    for status in ("active", "queued", "completed", "abandoned"):
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


def cmd_next_novel(args: argparse.Namespace) -> None:
    """Skip current novel, clean its data, and activate the next one."""
    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    queue = BookQueue(config, logger)
    clean = not getattr(args, "keep_output", False)
    novel = queue.skip_to_next_novel(clean_output=clean)
    print(f"Skipped previous novel. Now active: {novel.title} by {novel.author}")
    if novel.story_summary:
        print(f"\nStory summary:\n{novel.story_summary}")
    print(f"\nEpisodes planned: {novel.estimated_episodes}")
    print("Run: python main.py run  (to generate episode 1)")


def cmd_skip_episode(args: argparse.Namespace) -> None:
    """Mark current pending episode as done (use after manual upload or cache loss)."""
    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    queue = BookQueue(config, logger)
    ep = getattr(args, "episode", None)
    ctx = queue.skip_episode(episode_num=ep)
    print(
        f"Skipped to next: {ctx.novel.title} ep {ctx.episode.episode_num}/"
        f"{ctx.total_episodes}"
    )


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
    if not result["ok"]:
        print(f"❌ Meta connection failed: {result['error']}")
        print("\nRun: python main.py meta-setup  (after setting META_ACCESS_TOKEN in .env)")
        print("\nRequired .env vars:")
        print("  META_ACCESS_TOKEN  — EAA... token from Graph API Explorer (NOT Instagram Messaging token)")
        print("  META_IG_USER_ID    — Instagram Business account ID")
        print("  META_PAGE_ID       — Facebook Page ID (for cover image upload)")
        sys.exit(1)

    acct = result["account"]
    print("✅ Meta connection OK")
    print(f"  Instagram: @{acct.get('username', '?')} ({acct.get('name', '')})")
    print(f"  IG User ID: {acct.get('id')}")

    token_info = result.get("token_info") or {}
    if token_info.get("ok"):
        print(f"  Token type: {token_info.get('type')} | App ID: {token_info.get('app_id')}")
        scopes = token_info.get("scopes") or []
        if scopes:
            print(f"  Scopes: {', '.join(scopes)}")

    missing = result.get("missing_photo_permissions") or []
    if missing:
        print(f"\n⚠️  Missing for carousel/cover: {', '.join(missing)}")
        print("  Graph API Explorer → add permissions → Generate User token")
        print("  Then: python main.py meta-setup  (get fresh PAGE token)")

    photo = result.get("photo_probe") or {}
    if photo.get("ok"):
        print("✅ Page photo upload OK (carousel + thumbnail will work)")
    else:
        print(f"\n❌ Page photo upload failed: {photo.get('error', 'unknown')}")
        print("  Fix: add pages_manage_posts, regenerate token, run meta-setup again")
        sys.exit(1)


def cmd_meta_long_token(_: argparse.Namespace) -> None:
    """Get a Page token that does not expire (for .env + GitHub Secrets)."""
    import os

    from dotenv import load_dotenv

    from src.scheduler.meta import MetaScheduler

    load_dotenv()
    short_token = os.getenv("META_ACCESS_TOKEN", "").strip()
    app_id = os.getenv("META_APP_ID", "").strip()
    app_secret = os.getenv("META_APP_SECRET", "").strip()
    page_id = os.getenv("META_PAGE_ID", "").strip()

    if not short_token:
        print("Add a fresh SHORT-LIVED user token to META_ACCESS_TOKEN in .env first.")
        print("Get it from Graph API Explorer (expires in ~1 hour):")
        print("  https://developers.facebook.com/tools/explorer")
        sys.exit(1)

    if not app_id or not app_secret:
        print("META_APP_ID and META_APP_SECRET are required in .env")
        print("\nFind them: Meta Developers → Your App → App settings → Basic")
        print("  META_APP_ID=your_app_id")
        print("  META_APP_SECRET=your_app_secret")
        sys.exit(1)

    creds = MetaScheduler.validate_app_credentials(app_id, app_secret)
    if not creds["ok"]:
        print(f"❌ {creds['error']}")
        sys.exit(1)

    print("✅ App ID + App Secret verified")
    print("Exchanging short user token → long-lived user → permanent Page token...\n")
    result = MetaScheduler.obtain_permanent_page_token(
        short_token, app_id, app_secret, page_id=page_id
    )
    if not result["ok"]:
        print(f"❌ {result['error']}")
        sys.exit(1)

    token_info = result.get("token_info") or {}
    expires = token_info.get("expires_label", "?")

    print("✅ Permanent Page token ready\n")
    print(f"  Page: {result.get('page_name')} (META_PAGE_ID={result.get('page_id')})")
    if result.get("ig_user_id"):
        print(
            f"  Instagram: @{result.get('ig_username', '?')} "
            f"(META_IG_USER_ID={result.get('ig_user_id')})"
        )
    print(f"  Token expiry: {expires}")
    print("\nReplace META_ACCESS_TOKEN in .env AND GitHub Secret with this PAGE token:")
    print(result["page_token"])
    print("\nThis Page token should not expire unless you revoke the app or change password.")
    print("Then run: python main.py meta-test")


def cmd_meta_setup(_: argparse.Namespace) -> None:
    """Discover Page ID + Instagram ID from a Graph API user token."""
    import os

    from dotenv import load_dotenv

    from src.scheduler.meta import MetaScheduler

    load_dotenv()
    token = os.getenv("META_ACCESS_TOKEN", "").strip()
    page_id = os.getenv("META_PAGE_ID", "").strip()
    if not token:
        print("Add META_ACCESS_TOKEN to .env first, then run this command again.")
        print("\nHow to get the RIGHT token:")
        print("  1. https://developers.facebook.com/tools/explorer")
        print("  2. Select YOUR Meta app (not Instagram Messaging only)")
        print("  3. Permissions: instagram_basic, instagram_content_publish,")
        print("     pages_show_list, pages_read_engagement, pages_manage_posts")
        print("  4. Generate Access Token → copy token starting with EAA...")
        print("\nDo NOT use 'Generate token' on Instagram API → Messaging setup screen.")
        sys.exit(1)

    result = MetaScheduler.discover_accounts(token)
    if not result["ok"]:
        print(f"❌ {result['error']}")
        sys.exit(1)

    user = result["user"]
    pages = result["pages"]
    print(f"✅ Token valid for Facebook user: {user.get('name')} ({user.get('id')})")
    if not pages:
        if page_id:
            print(f"\nTrying to fetch Page token for META_PAGE_ID={page_id} ...")
            page_result = MetaScheduler.fetch_page_token(token, page_id)
            if page_result["ok"]:
                page = page_result["page"]
                page_token = page_result["page_token"]
                print(f"\n✅ Page token found for: {page.get('name')} ({page.get('id')})")
                print("\nReplace META_ACCESS_TOKEN in .env with this PAGE token:")
                print(page_token)
                print("\nThen run: python main.py meta-test")
                return
            print(f"\n❌ Could not get Page token: {page_result['error']}")

        print("\n❌ No Facebook Pages found for this Facebook account via API.")
        print("\nInstagram can show 'connected to Page' but the API only sees Pages")
        print("where THIS Facebook user is Admin/Editor:")
        print(f"  Logged in as: {user.get('name')} (ID {user.get('id')})")
        print("\nCommon fixes:")
        print("  1. Create a NEW Facebook Page while logged in as this same Facebook account:")
        print("     https://www.facebook.com/pages/create")
        print("     Name: Rahasya.exe | Category: Media/Brand")
        print("  2. Instagram app → Profile → Edit profile → Page → select that Page")
        print("  3. In Graph API Explorer, regenerate token with permissions:")
        print("     pages_show_list, pages_read_engagement, pages_manage_posts,")
        print("     instagram_basic, instagram_content_publish")
        print("  4. In Explorer, open 'User or Page' dropdown — if your Page appears,")
        print("     select the Page and generate a Page token instead.")
        print("\nIf the Page was created with a different Facebook login, either:")
        print("  - Log into Graph API Explorer with that Facebook account, OR")
        print("  - Add this account as Admin on the Page (Page Settings → Page access)")
        print("\nManual fallback (if you already have IDs from Meta developer dashboard):")
        print("  META_IG_USER_ID=17841437267653762   # from Instagram API setup")
        print("  META_PAGE_ID=<your Facebook Page numeric ID>")
        print("  Then run: python main.py meta-test")
        sys.exit(1)

    print("\nCopy these into .env and GitHub Secrets:\n")
    for page in pages:
        ig = (page.get("instagram_business_account") or {})
        print(f"Page: {page.get('name')} (META_PAGE_ID={page.get('id')})")
        if ig:
            print(f"  Instagram: @{ig.get('username', '?')} (META_IG_USER_ID={ig.get('id')})")
            page_token = page.get("access_token", "")
            if page_token:
                print(f"  Use this as META_ACCESS_TOKEN (Page token, best for posting):")
                print(f"  {page_token[:20]}...{page_token[-8:]}")
        else:
            print("  ⚠ No Instagram linked — link IG Business account to this Page in Instagram app")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rahasya.exe content pipeline")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Generate today's content")
    run_parser.add_argument(
        "--publish-now",
        action="store_true",
        help="Publish immediately after generate (skip min_publish_delay_hours)",
    )
    run_parser.add_argument(
        "--next-novel",
        action="store_true",
        help="Abandon current novel and activate the next queued one before generating",
    )
    run_parser.add_argument(
        "--keep-output",
        action="store_true",
        help="With --next-novel: keep output folders for the skipped novel",
    )
    run_parser.add_argument(
        "--regen-script",
        action="store_true",
        help="Ignore saved script_json and regenerate with the live writer",
    )
    run_parser.set_defaults(func=cmd_run)
    publish_parser = sub.add_parser(
        "publish",
        help="Post oldest queued bundle to Instagram (scheduled publish step)",
    )
    publish_parser.add_argument(
        "--now",
        action="store_true",
        help="Skip min_publish_delay_hours (for testing)",
    )
    publish_parser.set_defaults(func=cmd_publish)
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
    sub.add_parser(
        "meta-long-token",
        help="Get a Page token that does not expire (needs APP_ID + APP_SECRET)",
    ).set_defaults(func=cmd_meta_long_token)
    sub.add_parser(
        "meta-setup",
        help="Discover META_PAGE_ID and META_IG_USER_ID from Graph API token",
    ).set_defaults(func=cmd_meta_setup)

    add_parser = sub.add_parser("add-novel", help="Manually add a novel")
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--author", required=True)
    add_parser.add_argument("--country", default="")
    add_parser.add_argument("--chapters", type=int, default=20)
    add_parser.set_defaults(func=cmd_add_novel)

    next_parser = sub.add_parser(
        "next-novel",
        help="Skip current novel, clean its data, activate next in queue",
    )
    next_parser.add_argument(
        "--keep-output",
        action="store_true",
        help="Keep output folders for the skipped novel",
    )
    next_parser.set_defaults(func=cmd_next_novel)

    skip_ep = sub.add_parser(
        "skip-episode",
        help="Mark current pending episode done and advance (after manual upload)",
    )
    skip_ep.add_argument(
        "--episode",
        type=int,
        default=None,
        help="Episode number to skip (default: lowest pending)",
    )
    skip_ep.set_defaults(func=cmd_skip_episode)

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
