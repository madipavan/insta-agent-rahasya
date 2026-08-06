"""Seed assets/stock_library with thriller B-roll from Pixabay (free API)."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from src.config import load_config

THEMED_QUERIES: dict[str, list[str]] = {
    "night": ["night city cinematic dark", "night street noir", "dark alley night"],
    "rain": ["rain window cinematic", "rain night street", "storm rain moody"],
    "mansion": ["old mansion dark", "victorian house night", "haunted mansion exterior"],
    "detective": ["detective noir shadow", "mystery silhouette man", "crime scene tape dark"],
    "mystery": ["mystery fog forest", "suspense thriller cinematic", "dark corridor hallway"],
    "yellow_room": ["locked door mystery", "yellow room interior dark", "old study lamp night"],
}


def download_pixabay_clip(api_key: str, query: str, dest: Path) -> bool:
    resp = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": api_key, "q": query, "per_page": 5, "video_type": "film"},
        timeout=30,
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    random.shuffle(hits)
    for hit in hits:
        videos = hit.get("videos", {})
        url = None
        for quality in ("large", "medium", "small"):
            url = videos.get(quality, {}).get("url")
            if url:
                break
        if not url:
            continue
        vid_id = hit.get("id", random.randint(1, 99999))
        out = dest / f"pixabay_{vid_id}.mp4"
        if out.exists():
            return True
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        out.write_bytes(r.content)
        print(f"  saved {out.name} ({query})")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed stock_library from Pixabay")
    parser.add_argument("--per-folder", type=int, default=3, help="Clips per theme folder")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    config = load_config()
    api_key = config.pixabay_api_key
    if not api_key:
        print("PIXABAY_API_KEY missing in .env — add key from https://pixabay.com/api/docs/")
        sys.exit(1)

    library = config.path("stock_library")
    library.mkdir(parents=True, exist_ok=True)
    total = 0

    for folder, queries in THEMED_QUERIES.items():
        dest = library / folder
        dest.mkdir(parents=True, exist_ok=True)
        existing = list(dest.glob("*.mp4"))
        needed = max(0, args.per_folder - len(existing))
        if needed == 0:
            print(f"{folder}/ already has {len(existing)} clips")
            continue
        print(f"{folder}/ need {needed} clip(s)")
        saved = 0
        for query in queries:
            if saved >= needed:
                break
            if download_pixabay_clip(api_key, query, dest):
                saved += 1
                total += 1
        if saved < needed:
            print(f"  warning: only saved {saved}/{needed} for {folder}")

    print(f"Done — {total} new clip(s) in {library}")


if __name__ == "__main__":
    main()
