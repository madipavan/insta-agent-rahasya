"""Install manually downloaded music + SFX into the current novel cache.

No ElevenLabs API calls / no credits. You download from the ElevenLabs website
(or anywhere), then point this script at the files.

Usage:
  # Show where files should go for the active novel
  python scripts/install_novel_audio.py --show

  # Install BGM only
  python scripts/install_novel_audio.py --bgm "C:/Users/You/Downloads/tense_ambient.wav"

  # Install BGM + all 3 SFX
  python scripts/install_novel_audio.py ^
    --bgm "C:/Users/You/Downloads/music.wav" ^
    --hook "C:/Users/You/Downloads/hook.wav" ^
    --whoosh "C:/Users/You/Downloads/whoosh.wav" ^
    --cliffhanger "C:/Users/You/Downloads/cliff.wav"

  # Target a specific novel
  python scripts/install_novel_audio.py --novel-id 2 --bgm ./my_bgm.mp3
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.book_queue.store import Database
from src.config import load_config
from src.novel_assets.manager import NovelAssetManager
from src.pipeline.logger import PipelineLogger
from src.utils.ffmpeg_path import get_ffmpeg_exe
from src.visuals.sfx import SFX_FILES


def _resolve_novel(db: Database, novel_id: int | None, title: str):
    if novel_id is not None:
        novel = db.get_novel(novel_id)
        if not novel:
            raise SystemExit(f"Novel id={novel_id} not found")
        return novel
    if title:
        for n in db.list_novels():
            if n.title.lower() == title.lower():
                return n
        raise SystemExit(f"Novel title not found: {title}")
    novel = db.get_active_novel()
    if not novel:
        raise SystemExit("No active novel — pass --novel-id or --title")
    return novel


def _ffmpeg_convert(src: Path, dest: Path, *, as_wav: bool) -> None:
    ffmpeg = get_ffmpeg_exe()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if as_wav:
        cmd = [
            ffmpeg, "-y", "-i", str(src),
            "-ac", "1", "-ar", "44100",
            str(dest),
        ]
    else:
        cmd = [
            ffmpeg, "-y", "-i", str(src),
            "-vn", "-c:a", "libmp3lame", "-q:a", "2",
            "-ar", "44100", "-ac", "2",
            str(dest),
        ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ffmpeg failed for {src.name}: {result.stderr[-800:]}")


def _write_bgm_meta(dest: Path, novel_title: str, src: Path) -> None:
    dest.with_suffix(".json").write_text(
        json.dumps(
            {
                "novel": novel_title,
                "source": "manual",
                "title": src.name,
                "search": "manual install",
                "url": "",
                "imported_from": str(src),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_sfx_meta(sfx_dir: Path, novel_title: str, files: list[str]) -> None:
    (sfx_dir / "sfx.json").write_text(
        json.dumps(
            {
                "novel": novel_title,
                "source": "manual",
                "files": files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install manually downloaded BGM/SFX for a novel (no API credits)"
    )
    parser.add_argument("--novel-id", type=int, default=None)
    parser.add_argument("--title", type=str, default="")
    parser.add_argument("--show", action="store_true", help="Print target folders and exit")
    parser.add_argument("--bgm", type=str, default="", help="Path to music/ambient file")
    parser.add_argument("--hook", type=str, default="", help="Path to hook impact SFX")
    parser.add_argument("--whoosh", type=str, default="", help="Path to whoosh SFX")
    parser.add_argument("--cliffhanger", type=str, default="", help="Path to cliffhanger SFX")
    args = parser.parse_args()

    config = load_config()
    db = Database(config.path("db_path"))
    logger = PipelineLogger(config.path("logs_dir"))
    mgr = NovelAssetManager(config, logger, db)
    novel = _resolve_novel(db, args.novel_id, args.title)
    novel_dir = mgr._novel_dir(novel)
    novel_dir.mkdir(parents=True, exist_ok=True)
    sfx_dir = novel_dir / "sfx"
    bgm_path = novel_dir / "bgm.mp3"

    print(f"Novel: {novel.title} (id={novel.id})")
    print(f"Folder: {novel_dir}")
    print(f"  BGM  -> {bgm_path}")
    print(f"  SFX  -> {sfx_dir}/")
    for name in SFX_FILES.values():
        print(f"         {name}")

    if args.show:
        return

    if not any([args.bgm, args.hook, args.whoosh, args.cliffhanger]):
        print("\nNothing to install. Pass --bgm / --hook / --whoosh / --cliffhanger")
        print("Or run with --show to see paths.")
        sys.exit(1)

    installed: list[str] = []

    if args.bgm:
        src = Path(args.bgm).expanduser().resolve()
        if not src.exists():
            raise SystemExit(f"BGM file not found: {src}")
        _ffmpeg_convert(src, bgm_path, as_wav=False)
        _write_bgm_meta(bgm_path, novel.title, src)
        db.set_novel_assets(
            novel.id,
            str(bgm_path),
            db.get_novel_thumbnail_base(novel.id) or "",
        )
        installed.append(f"BGM <- {src.name} ({bgm_path.stat().st_size} bytes)")

    sfx_map = {
        "hook_impact": args.hook,
        "whoosh_short": args.whoosh,
        "cliffhanger_rumble": args.cliffhanger,
    }
    sfx_installed: list[str] = []
    if any(sfx_map.values()):
        sfx_dir.mkdir(parents=True, exist_ok=True)
        for key, path_str in sfx_map.items():
            if not path_str:
                continue
            src = Path(path_str).expanduser().resolve()
            if not src.exists():
                raise SystemExit(f"SFX file not found: {src}")
            dest = sfx_dir / SFX_FILES[key]
            # Copy if already wav-ish and short; otherwise convert
            if src.suffix.lower() == ".wav":
                shutil.copy2(src, dest)
            else:
                _ffmpeg_convert(src, dest, as_wav=True)
            sfx_installed.append(SFX_FILES[key])
            installed.append(f"SFX {key} <- {src.name} ({dest.stat().st_size} bytes)")

        # Keep existing files in meta if partially updating
        present = [n for n in SFX_FILES.values() if (sfx_dir / n).exists()]
        _write_sfx_meta(sfx_dir, novel.title, present)

    print("\nInstalled:")
    for line in installed:
        print(f"  ✓ {line}")
    print("\nThese will be reused for every episode of this novel.")
    print("No ElevenLabs credits were used.")


if __name__ == "__main__":
    main()
