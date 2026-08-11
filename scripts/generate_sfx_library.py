"""Generate retention SFX locally via ffmpeg — no ElevenLabs API / no credits.

The pipeline expects three short WAV files in assets/sfx_library/:
  hook_impact.wav, whoosh_short.wav, cliffhanger_rumble.wav

ElevenLabs *does* offer text-to-sound-effects (client.text_to_sound_effects.convert),
but each API generation costs credits (~100 per effect by default). This script
uses the same ffmpeg synthesis as src/visuals/sfx.py instead.

Usage:
  python scripts/generate_sfx_library.py          # create missing files only
  python scripts/generate_sfx_library.py --force  # regenerate all three
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.pipeline.logger import PipelineLogger
from src.visuals.sfx import SFX_FILES, SfxMixer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate local retention SFX (ffmpeg, no API credits)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate all SFX even if files already exist",
    )
    args = parser.parse_args()

    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    mixer = SfxMixer(config, logger)
    library = mixer.library_dir
    library.mkdir(parents=True, exist_ok=True)

    if args.force:
        for filename in SFX_FILES.values():
            path = library / filename
            if path.exists():
                path.unlink()
                print(f"removed {path.name}")

    mixer.ensure_library()

    created = [f for f in SFX_FILES.values() if (library / f).exists()]
    print(f"Done — {len(created)} file(s) in {library}")
    for name in created:
        path = library / name
        print(f"  {name} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
