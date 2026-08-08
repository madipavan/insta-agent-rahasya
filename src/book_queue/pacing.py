"""Episode pacing calculations."""

from __future__ import annotations


def estimate_episode_count(chapter_count: int, max_episodes: int = 12) -> int:
    """Clamp episode count to 8–max_episodes (default max 12) based on chapters."""
    cap = max(8, min(12, int(max_episodes or 12)))
    if chapter_count <= 0:
        return cap
    scaled = round(chapter_count * 0.8)
    return max(8, min(cap, scaled))


def chapter_ranges(chapter_count: int, episode_count: int) -> list[tuple[int, int]]:
    """Distribute chapters across episodes as evenly as possible."""
    ranges: list[tuple[int, int]] = []
    chapters = max(chapter_count, episode_count)
    base = chapters // episode_count
    remainder = chapters % episode_count
    start = 1
    for i in range(episode_count):
        span = base + (1 if i < remainder else 0)
        end = start + span - 1
        ranges.append((start, end))
        start = end + 1
    return ranges
