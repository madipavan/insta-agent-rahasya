"""Shared novel slug for bundle IDs and output folder matching."""

from __future__ import annotations

import re


def slugify_novel(title: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_")
    return (slug[:max_len] if slug else "novel")
