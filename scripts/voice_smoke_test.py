"""Quick Fish Audio voice smoke test."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.pipeline.logger import PipelineLogger
from src.voiceover.provider import get_voiceover_provider

SAMPLE = (
    "उस रात कमरे की चाबी अंदर से बंद थी। "
    "फिर भी कोई अंदर था… और वो किसी को देखना नहीं चाहता था।"
)


def main() -> None:
    config = load_config()
    logger = PipelineLogger(config.path("logs_dir"))
    provider_name = config.voice_provider.replace("-", "_")
    out = config.path("output_dir") / f"{provider_name}_smoke_test.mp3"
    provider = get_voiceover_provider(config, logger)
    provider.generate(SAMPLE, out)
    print(f"OK: {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
