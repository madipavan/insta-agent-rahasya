"""Brand hashtag lock + typo rewrite helpers."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

DEFAULT_BRAND_HASHTAG = "#RahasyaExe"

# Known misspellings / casing variants of the brand tag
_VARIANT_RE = re.compile(
    r"#\s*raha[ys]?ya?\s*exe|#\s*rahays?a\s*exe|#\s*rahasya\s*exe",
    re.IGNORECASE,
)

# Explicit bad forms we always rewrite
KNOWN_VARIANTS = (
    "#rahaysaexe",
    "#rahasyaexe",
    "#Rahasyaexe",
    "#RAHASYAEXE",
    "#RahaysaExe",
    "#RAHAYSAEXE",
    "#RahasyaEXE",
    "#rahasyaExe",
)


def normalize_brand_hashtag(
    text: str,
    locked: str = DEFAULT_BRAND_HASHTAG,
    *,
    log: logging.Logger | None = None,
) -> tuple[str, bool]:
    """Rewrite known brand-hashtag variants to the locked spelling.

    Returns (normalized_text, found_variant).
    """
    if not text:
        return text, False
    locked = (locked or DEFAULT_BRAND_HASHTAG).strip() or DEFAULT_BRAND_HASHTAG
    found = False
    result = text

    for variant in KNOWN_VARIANTS:
        if variant.lower() == locked.lower() and variant == locked:
            continue
        pattern = re.compile(re.escape(variant), re.IGNORECASE)
        if pattern.search(result):
            found = True
            result = pattern.sub(locked, result)

    # Catch spacing / soft variants
    def _repl(match: re.Match[str]) -> str:
        nonlocal found
        raw = re.sub(r"\s+", "", match.group(0))
        if raw != locked:
            found = True
            return locked
        return locked if raw.lower() == locked.lower() else match.group(0)

    result2 = _VARIANT_RE.sub(_repl, result)
    if result2 != result:
        found = True
        result = result2

    # Force exact casing if a case-insensitive match of the locked tag exists
    exact_re = re.compile(re.escape(locked), re.IGNORECASE)
    if exact_re.search(result):
        before = result
        result = exact_re.sub(locked, result)
        if result != before and before.lower().count(locked.lower()) > 0:
            # Casing-only fix still counts as a rewrite when not already exact
            if locked not in before:
                found = True

    if found:
        (log or logger).warning(
            "Rewrote brand hashtag variant(s) → %s", locked
        )
    return result, found
