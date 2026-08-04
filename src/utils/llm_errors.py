"""Detect LLM quota / rate-limit errors for provider fallback."""

from __future__ import annotations


def is_llm_limit_error(exc: BaseException) -> bool:
    """True when the error indicates quota exhaustion or rate limiting."""
    err = str(exc).lower()
    markers = (
        "rate_limit",
        "rate limit",
        "ratelimit",
        "429",
        "413",
        "quota",
        "resource_exhausted",
        "resource exhausted",
        "tokens per day",
        "tpm",
        "tpd",
        "too many requests",
        "limit exceeded",
        "insufficient_quota",
        "capacity",
        "overloaded",
    )
    return any(m in err for m in markers)
