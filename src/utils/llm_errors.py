"""Detect LLM quota / auth / rate-limit errors for provider fallback."""

from __future__ import annotations


def is_llm_limit_error(exc: BaseException) -> bool:
    """True when the error should trigger switching to the next LLM provider."""
    err = str(exc).lower()
    markers = (
        "rate_limit",
        "rate limit",
        "ratelimit",
        "429",
        "403",
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
        "permission-denied",
        "permission_denied",
        "permission denied",
        "doesn't have any credits",
        "does not have any credits",
        "no credits",
        "licenses yet",
        "billing",
        "payment required",
        "401",
        "unauthorized",
        "invalid api key",
        "incorrect api key",
    )
    return any(m in err for m in markers)
