"""Episode pacing calculations."""

from __future__ import annotations


def estimate_episode_count(chapter_count: int) -> int:
    """Clamp episode count to 14-21 based on chapter count."""
    if chapter_count <= 0:
        return 14
    scaled = round(chapter_count * 0.8)
    return max(14, min(21, scaled))


def chapter_ranges(chapter_count: int, episode_count: int) -> list[tuple[int, int]]:
    """Distribute chapters across episodes as evenly as possible."""
    ranges: list[tuple[int, int]] = []
    base = chapter_count // episode_count
    remainder = chapter_count % episode_count
    start = 1
    for i in range(episode_count):
        span = base + (1 if i < remainder else 0)
        end = start + span - 1
        ranges.append((start, end))
        start = end + 1
    return ranges
