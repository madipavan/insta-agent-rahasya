"""Generate / refresh per-novel ElevenLabs music + SFX (uses credits once).

Usage:
  python scripts/generate_novel_audio.py --novel-id 1
  python scripts/generate_novel_audio.py --novel-id 1 --force
  python scripts/generate_novel_audio.py --title "The Riddle of the Sands"
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.book_queue.store import Database
from src.config import load_config
from src.novel_assets.manager import NovelAssetManager
from src.pipeline.logger import PipelineLogger


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-novel ElevenLabs music + SFX")
    parser.add_argument("--novel-id", type=int, default=None)
    parser.add_argument("--title", type=str, default="")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete cached bgm.mp3 and sfx/ so ElevenLabs regenerates",
    )
    parser.add_argument(
        "--keywords",
        type=str,
        default="mystery,thriller,suspense,dark",
        help="Comma-separated mood keywords",
    )
    args = parser.parse_args()

    config = load_config()
    if not config.elevenlabs_api_key:
        print("ERROR: ELEVENLABS_API_KEY missing in .env")
        sys.exit(1)
    if not config.video.elevenlabs_audio_enabled:
        print("ERROR: video.elevenlabs_audio_enabled is false in config.yaml")
        sys.exit(1)

    logger = PipelineLogger(config.path("logs_dir"))
    db = Database(config.path("db_path"))
    mgr = NovelAssetManager(config, logger, db)

    novel = None
    if args.novel_id is not None:
        novel = db.get_novel(args.novel_id)
    elif args.title:
        for n in db.list_novels():
            if n.title.lower() == args.title.lower():
                novel = n
                break
    else:
        novel = db.get_active_novel()

    if not novel:
        print("ERROR: novel not found (pass --novel-id or --title)")
        sys.exit(1)

    novel_dir = mgr._novel_dir(novel)
    if args.force:
        for path in (novel_dir / "bgm.mp3", novel_dir / "bgm.json"):
            path.unlink(missing_ok=True)
        sfx = novel_dir / "sfx"
        if sfx.exists():
            shutil.rmtree(sfx)
        print(f"Cleared cache under {novel_dir}")

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    print(f"Generating audio for: {novel.title} (id={novel.id})")
    assets = mgr.ensure(novel, keywords)
    print(f"BGM: {assets.bgm_path}")
    print(f"SFX: {assets.sfx_dir}")
    print("Done. Cached for all episodes of this novel.")


if __name__ == "__main__":
    main()
