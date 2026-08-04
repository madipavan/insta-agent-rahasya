"""Extract plain text from LangChain chat model responses."""

from __future__ import annotations

from typing import Any


def extract_llm_text(response: Any) -> str:
    """Normalize AIMessage content to a string (handles list blocks / empty content)."""
    content = getattr(response, "content", "")
    if isinstance(content, str):
        text = content.strip()
        if text:
            return text

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                if block.strip():
                    parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            if block.get("thought") or block.get("extras", {}).get("thought"):
                continue
            if block.get("type") == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    parts.append(text)
        joined = "".join(parts).strip()
        if joined:
            return joined

    extra = getattr(response, "additional_kwargs", {}) or {}
    for key in ("text", "reasoning_content"):
        value = extra.get(key)
        if value:
            return str(value).strip()

    return ""
