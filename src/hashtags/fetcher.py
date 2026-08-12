"""Fetch and rank Instagram hashtags for posting."""

from __future__ import annotations

import re

from src.book_queue.models import EpisodeContext
from src.config import AppConfig
from src.hashtags.brand import DEFAULT_BRAND_HASHTAG, normalize_brand_hashtag
from src.pipeline.logger import PipelineLogger
from src.scheduler.meta import MetaScheduler

# High-performing book/thriller tags (updated periodically)
CURATED_HASHTAGS = [
    "#booktok",
    "#bookstagram",
    "#thrillerbooks",
    "#suspensenovel",
    "#mysterybooks",
    "#bookreels",
    "#hindibooks",
    "#hindithriller",
    "#suspensestory",
    "#storytime",
    "#booklover",
    "#readersofinstagram",
    "#thriller",
    "#suspense",
    "#bookish",
    "#novel",
    "#fiction",
    "#bookcommunity",
    "#instabooks",
    "#bookaddict",
]

SEARCH_QUERIES = [
    "booktok",
    "thrillerbooks",
    "suspense",
    "bookstagram",
    "mystery",
    "hindibooks",
    "bookreels",
    "storytime",
    "suspensenovel",
    "booklover",
]


def _slug_hashtag(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "", text.lower())
    return f"#{slug}" if slug else ""


class HashtagFetcher:
    """Build ranked hashtag set: curated + Meta search + episode/novel specific."""

    MAX_HASHTAGS = 30

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.meta = MetaScheduler(config, logger)

    def build(
        self,
        context: EpisodeContext,
        *,
        extra_keywords: list[str] | None = None,
    ) -> str:
        ep = context.episode.episode_num
        novel = context.novel.title
        author = context.novel.author

        base = self._parse_base_tags(self.config.hashtags)
        curated = [t for t in CURATED_HASHTAGS if t.lower() not in {b.lower() for b in base}]

        episode_tags = [
            f"#ep{ep}",
            _slug_hashtag(novel),
            _slug_hashtag(author),
            getattr(self.config, "brand_hashtag", DEFAULT_BRAND_HASHTAG) or DEFAULT_BRAND_HASHTAG,
        ]

        search_queries = list(SEARCH_QUERIES)
        if extra_keywords:
            search_queries.extend(kw.lower() for kw in extra_keywords[:5])

        meta_tags: list[str] = []
        if self.meta.is_configured():
            try:
                meta_tags = self.meta.search_hashtags(search_queries, limit=12)
                self.logger.info(f"Meta hashtag search returned {len(meta_tags)} tags")
            except Exception as exc:
                self.logger.warn("hashtags", f"Meta search failed: {exc}")

        ranked = self._rank_and_dedupe(base, meta_tags, curated, episode_tags)
        joined = " ".join(ranked[: self.MAX_HASHTAGS])
        locked = getattr(self.config, "brand_hashtag", DEFAULT_BRAND_HASHTAG) or DEFAULT_BRAND_HASHTAG
        joined, _ = normalize_brand_hashtag(joined, locked)
        return joined

    def _parse_base_tags(self, raw: str) -> list[str]:
        tags = []
        for part in raw.split():
            part = part.strip()
            if part and not part.startswith("#"):
                part = f"#{part}"
            if part:
                tags.append(part)
        return tags

    def _rank_and_dedupe(
        self,
        base: list[str],
        meta: list[str],
        curated: list[str],
        episode: list[str],
    ) -> list[str]:
        """Priority: base config → Meta API results → curated → episode-specific."""
        seen: set[str] = set()
        result: list[str] = []

        for group in (base, meta, curated, episode):
            for tag in group:
                key = tag.lower().lstrip("#")
                if not key or key in seen:
                    continue
                seen.add(key)
                result.append(tag if tag.startswith("#") else f"#{tag}")

        return result
