#!/usr/bin/env python3
"""Sleep until config.post_time in config.timezone (used by CI before publish)."""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402


def main() -> None:
    config = load_config()
    tz = ZoneInfo(config.timezone)
    now = datetime.now(tz)
    hour, minute = map(int, config.post_time.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if now >= target:
        print(f"Already past {config.post_time} {config.timezone} — publishing now")
        return

    wait_sec = int((target - now).total_seconds())
    print(f"Waiting {wait_sec}s until {config.post_time} {config.timezone} ({target.isoformat()})")
    time.sleep(wait_sec)
    print("Post time reached")


if __name__ == "__main__":
    main()
