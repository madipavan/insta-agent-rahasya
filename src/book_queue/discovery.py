"""Automatic novel discovery from public domain sources."""

from __future__ import annotations

import re
from typing import Any

import requests

from src.book_queue.store import Database
from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.provider import get_provider


GUTENBERG_SEARCH = "https://gutendex.com/books"
TMDB_SEARCH = "https://api.themoviedb.org/3/search/multi"
HTTP_HEADERS = {
    "User-Agent": "Rahasya.exe/1.0 (https://github.com/madipavan/insta-agent-rahasya; content-bot)",
    "Accept": "application/json",
}

# Curated public-domain thriller/suspense keywords for Gutenberg search
SEARCH_TERMS = [
    "mystery",
    "thriller",
    "detective",
    "suspense",
    "crime",
    "horror",
]


class NovelDiscovery:
    def __init__(
        self,
        config: AppConfig,
        db: Database,
        logger: PipelineLogger,
    ) -> None:
        self.config = config
        self.db = db
        self.logger = logger

    def run(self) -> int:
        self.logger.start("discovery", "scanning public domain sources")
        candidates = self._fetch_gutenberg_candidates()
        added = 0
        for candidate in candidates:
            if added >= self.config.discovery.batch_size:
                break
            title = candidate["title"]
            author = candidate["author"]
            if self.db.novel_exists(title, author):
                continue

            if self._has_adaptation(title, author):
                self.db.log_discovery(title, author, "rejected", "TMDB adaptation found")
                continue

            if not self._passes_niche_filter(candidate):
                self.db.log_discovery(title, author, "rejected", "Failed niche filter")
                continue

            novel_id = self.db.add_novel(
                title=title,
                author=author,
                country=candidate.get("country", ""),
                chapter_count=candidate.get("chapter_count", 20),
                public_domain=True,
                source_link=candidate.get("source_link", ""),
                adaptation_checked=True,
                status="queued",
            )
            self.db.log_discovery(title, author, "queued", f"novel_id={novel_id}")
            added += 1
            self.logger.info(f"Queued novel: {title} by {author}")

        self.logger.ok("discovery", f"added {added} novels")
        return added

    def _fetch_gutenberg_candidates(self) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()

        for term in SEARCH_TERMS:
            try:
                resp = requests.get(
                    GUTENBERG_SEARCH,
                    params={"search": term, "languages": "en"},
                    headers=HTTP_HEADERS,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as exc:
                self.logger.warn("discovery", f"Gutenberg fetch failed: {exc}")
                continue

            for book in data.get("results", []):
                title = book.get("title", "").strip()
                authors = book.get("authors", [])
                if not title or not authors:
                    continue
                author = authors[0].get("name", "").strip()
                key = f"{title}|{author}".lower()
                if key in seen:
                    continue
                seen.add(key)

                # Estimate chapters from download count or default
                chapter_count = max(15, min(40, len(book.get("formats", {})) * 3 + 12))
                candidates.append(
                    {
                        "title": title,
                        "author": author,
                        "country": self._infer_country(author),
                        "chapter_count": chapter_count,
                        "source_link": f"https://gutendex.com/books/{book.get('id', '')}",
                    }
                )

        return candidates

    def _infer_country(self, author: str) -> str:
        # Simple heuristic — LLM filter does the real work
        if any(x in author.lower() for x in ["doyle", "christie", "hammett", "chandler"]):
            return "UK/US"
        return "Foreign"

    def _has_adaptation(self, title: str, author: str) -> bool:
        if not self.config.tmdb_api_key:
            self.logger.warn("discovery", "No TMDB API key — skipping adaptation check")
            return False

        query = f"{title} {author}"
        try:
            resp = requests.get(
                TMDB_SEARCH,
                params={"api_key": self.config.tmdb_api_key, "query": query},
                headers=HTTP_HEADERS,
                timeout=20,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except requests.RequestException as exc:
            self.logger.warn("discovery", f"TMDB check failed: {exc}")
            return False

        title_lower = title.lower()
        for result in results[:5]:
            media_type = result.get("media_type", "")
            if media_type not in ("movie", "tv"):
                continue
            result_title = (result.get("title") or result.get("name") or "").lower()
            if self._titles_match(title_lower, result_title):
                return True
        return False

    def _titles_match(self, a: str, b: str) -> bool:
        if not a or not b:
            return False
        a_clean = re.sub(r"[^a-z0-9 ]", "", a)
        b_clean = re.sub(r"[^a-z0-9 ]", "", b)
        return a_clean in b_clean or b_clean in a_clean or a_clean == b_clean

    def _passes_niche_filter(self, candidate: dict[str, Any]) -> bool:
        try:
            provider = get_provider(self.config)
            prompt = (
                f"Title: {candidate['title']}\n"
                f"Author: {candidate['author']}\n"
                f"Country hint: {candidate.get('country', '')}\n\n"
                "Is this a foreign (non-Indian) suspense/thriller/mystery novel "
                "suitable for a page about unadapted thrillers? "
                "Reply with only YES or NO."
            )
            response = provider.complete(prompt, max_tokens=10)
            return "yes" in response.lower()
        except Exception as exc:
            self.logger.warn("discovery", f"Niche filter failed: {exc}")
            return True
