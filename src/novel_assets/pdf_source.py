"""Download novel PDF (Gutenberg) and extract text for LLM summarization."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger

GUTENDEX_BOOK = "https://gutendex.com/books/{book_id}"
HTTP_HEADERS = {
    "User-Agent": "Rahasya.exe/1.0 (https://github.com/madipavan/insta-agent-rahasya; content-bot)",
    "Accept": "*/*",
}

# Prefer PDF; text formats used to build a PDF when none exists.
_PDF_MIME_HINTS = ("application/pdf",)
_TEXT_MIME_HINTS = (
    "text/plain",
    "text/plain; charset=utf-8",
    "text/html",
    "application/epub+zip",
)


def parse_gutenberg_book_id(source_link: str) -> str | None:
    """Extract Gutenberg / gutendex book id from a source URL."""
    if not source_link:
        return None
    text = source_link.strip()
    m = re.search(r"(?:gutendex\.com/books/|gutenberg\.org/(?:ebooks|files)/)(\d+)", text)
    if m:
        return m.group(1)
    if text.isdigit():
        return text
    return None


def extract_pdf_text(pdf_path: Path, max_chars: int = 200_000) -> str:
    """Extract plain text from a local PDF (truncated for LLM context)."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        if total + len(page_text) > max_chars:
            remain = max_chars - total
            if remain > 0:
                parts.append(page_text[:remain])
            break
        parts.append(page_text)
        total += len(page_text)
    return "\n\n".join(parts).strip()


def text_to_pdf(text: str, dest: Path, title: str = "Novel") -> Path:
    """Write plain text into a simple PDF so the artifact is always a PDF."""
    from fpdf import FPDF

    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    # fpdf core fonts are Latin-1; strip/replace unsupported chars.
    safe_title = title.encode("latin-1", "replace").decode("latin-1")
    safe_body = text.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 6, f"{safe_title}\n\n{safe_body[:120000]}")
    pdf.output(str(dest))
    return dest


class NovelPdfSource:
    """Ensure a novel has a local PDF and return extractable text."""

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger

    def novels_dir(self, novel_id: int) -> Path:
        base = self.config.path("novels_pdf_dir")
        path = base / str(novel_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_pdf(self, novel_id: int, title: str, source_link: str) -> Path:
        """Download or build book.pdf under data/novels/{id}/."""
        dest = self.novels_dir(novel_id) / "book.pdf"
        if dest.exists() and dest.stat().st_size > 1000:
            self.logger.info(f"pdf_source | using cached PDF {dest}")
            return dest

        book_id = parse_gutenberg_book_id(source_link)
        formats = self._fetch_formats(book_id) if book_id else {}
        if not formats and book_id:
            formats = self._gutenberg_direct_formats(book_id)
            if formats:
                self.logger.info(f"pdf_source | using direct Gutenberg URLs for book {book_id}")
        pdf_url = self._pick_url(formats, _PDF_MIME_HINTS)
        if pdf_url:
            self.logger.start("pdf_source", f"downloading PDF for novel {novel_id}")
            self._download_binary(pdf_url, dest)
            if dest.exists() and dest.stat().st_size > 1000:
                self.logger.ok("pdf_source", f"saved {dest.name} ({dest.stat().st_size} bytes)")
                return dest

        text_url = self._pick_url(formats, _TEXT_MIME_HINTS)
        if not text_url and source_link.startswith("http") and source_link.lower().endswith(".pdf"):
            self._download_binary(source_link, dest)
            if dest.exists() and dest.stat().st_size > 1000:
                return dest

        if not text_url:
            raise RuntimeError(
                f"No PDF or text download found for novel {novel_id} "
                f"(source={source_link!r})"
            )

        self.logger.start("pdf_source", f"building PDF from text for novel {novel_id}")
        raw = self._download_text(text_url)
        if not raw.strip():
            raise RuntimeError(f"Empty text download for novel {novel_id}")
        text_to_pdf(raw, dest, title=title)
        self.logger.ok("pdf_source", f"built PDF from text ({dest.stat().st_size} bytes)")
        return dest

    def load_text(self, pdf_path: Path, max_chars: int = 200_000) -> str:
        text = extract_pdf_text(pdf_path, max_chars=max_chars)
        if not text:
            raise RuntimeError(f"No extractable text in PDF: {pdf_path}")
        return text

    def _fetch_formats(self, book_id: str) -> dict[str, str]:
        try:
            resp = requests.get(
                GUTENDEX_BOOK.format(book_id=book_id),
                headers={**HTTP_HEADERS, "Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            formats = data.get("formats") or {}
            return {str(k): str(v) for k, v in formats.items() if v}
        except requests.RequestException as exc:
            self.logger.warn("pdf_source", f"gutendex formats failed: {exc}")
            return {}

    def _gutenberg_direct_formats(self, book_id: str) -> dict[str, str]:
        """Fallback when Gutendex is blocked on CI (403 from GitHub Actions IPs)."""
        return {
            "application/pdf": f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.pdf",
            "text/plain; charset=utf-8": (
                f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
            ),
            "text/html": f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}-h.htm",
        }

    def _pick_url(self, formats: dict[str, str], mime_hints: tuple[str, ...]) -> str | None:
        # Exact / prefix match first
        lower_map = {k.lower(): v for k, v in formats.items()}
        for hint in mime_hints:
            for key, url in lower_map.items():
                if key.startswith(hint.lower()) or hint.lower() in key:
                    if url and url.startswith("http"):
                        return url
        # Filename fallback
        for url in formats.values():
            path = urlparse(url).path.lower()
            if any(h.split("/")[-1] in path for h in mime_hints):
                return url
        return None

    def _download_binary(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, headers=HTTP_HEADERS, timeout=120, stream=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

    def _download_text(self, url: str) -> str:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=120)
        resp.raise_for_status()
        # Prefer declared encoding; fall back to utf-8 / latin-1
        resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        text = resp.text
        # Strip basic HTML if needed
        if "<html" in text[:500].lower() or url.lower().endswith(".htm") or ".htm." in url.lower():
            text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
            text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
        return text.strip()
