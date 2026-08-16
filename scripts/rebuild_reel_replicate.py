"""Rebuild an existing episode reel with Replicate stills only (no TTS/LLM)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.book_queue.models import EpisodeContext, ScriptOutput
from src.book_queue.store import Database
from src.config import load_config
from src.novel_assets.manager import NovelAssetManager
from src.pipeline.logger import PipelineLogger
from src.script_gen.export import write_script_txt
from src.static_post.generator import StaticPostGenerator
from src.visuals.assembler import ReelAssembler
from src.visuals.stock import StockResolver


def main() -> None:
    episode_num = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    bundle_id = (
        sys.argv[2]
        if len(sys.argv) > 2
        else f"20260817_the_riddle_of_the_sands_ep{episode_num}"
    )

    cfg = load_config()
    log = PipelineLogger(cfg.path("logs_dir"))
    db = Database(cfg.path("db_path"))
    novel = db.get_active_novel()
    if not novel:
        raise SystemExit("No active novel")
    ep = db.get_episode(novel.id, episode_num)
    if not ep:
        raise SystemExit(f"Episode {episode_num} not found")

    raw = db.get_episode_script_json(novel.id, episode_num)
    work = cfg.path("output_dir") / "work" / bundle_id
    review_meta = cfg.path("output_dir") / "review" / bundle_id / "metadata.json"
    if not raw and review_meta.exists():
        raw = json.dumps(json.loads(review_meta.read_text(encoding="utf-8")).get("script") or {})
    if not raw or raw in ("{}", "null"):
        raise SystemExit(f"No script_json for ep{episode_num} (DB or review metadata)")
    script = ScriptOutput.from_dict(json.loads(raw) if isinstance(raw, str) else raw)
    ctx = EpisodeContext(
        novel=novel,
        episode=ep,
        total_episodes=novel.estimated_episodes or cfg.max_episodes,
    )

    voice = work / "voiceover.mp3"
    if not voice.exists():
        raise SystemExit(f"Missing voiceover (won't regenerate): {voice}")

    print(
        f"Rebuild {bundle_id}: Replicate stills-only "
        f"(model={cfg.replicate_art.model}, n={cfg.replicate_art.reel_still_count})"
    )
    print("Skipping ElevenLabs / LLM / discovery")

    stock = StockResolver(cfg, log)
    stills = stock.resolve_visuals(script.stock_keywords, work)
    print("visuals:", len(stills), [p.name for p in stills])
    if not stills:
        raise SystemExit("No visuals generated")
    if any(p.suffix.lower() in (".mp4", ".mov", ".webm") for p in stills):
        raise SystemExit("Got stock video — expected Replicate stills only")

    manager = NovelAssetManager(cfg, log, db, stock=stock)
    assets = manager.ensure(novel, script.stock_keywords)
    hook = script.on_screen_text[0] if script.on_screen_text else script.hook
    thumb = manager.episode_thumbnail(
        novel,
        episode_num,
        ctx.total_episodes,
        work / "thumbnail.png",
        assets=assets,
        hook_text=hook,
    )

    reel = ReelAssembler(cfg, log).assemble(
        ctx,
        script,
        voice,
        stills,
        work / "reel.mp4",
        bgm_path=assets.bgm_path,
        sfx_dir=assets.sfx_dir,
    )
    print(f"reel: {reel} ({reel.stat().st_size:,} bytes)")

    static_paths = StaticPostGenerator(cfg, log).generate_all(
        ctx, script, work, stills
    )
    print(f"static: {len(static_paths)} slides")

    write_script_txt(ctx, script, work / "script.txt")

    dest = cfg.path("output_dir") / "review" / bundle_id
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("reel.mp4", "thumbnail.png", "script.txt", "voiceover.mp3"):
        src = work / name
        if src.exists():
            shutil.copy2(src, dest / name)
    for p in static_paths:
        shutil.copy2(p, dest / p.name)
    if (work / "static_post.png").exists():
        shutil.copy2(work / "static_post.png", dest / "static_post.png")

    print(f"OK: {dest / 'reel.mp4'}")


if __name__ == "__main__":
    main()
