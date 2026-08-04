"""Extract plain text from LangChain chat model responses."""

from __future__ import annotations

from typing import Any


def extract_llm_text(response: Any) -> str:
    """Normalize AIMessage content to a string (handles list blocks / empty content)."""
    direct = getattr(response, "text", None)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

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
            block_type = str(block.get("type", "")).lower()
            if block_type in {"thinking", "reasoning"}:
                continue
            if block.get("thought") or block.get("thinking"):
                continue
            if block.get("extras", {}).get("thought"):
                continue
            text_val = block.get("text")
            if text_val:
                parts.append(str(text_val))
        joined = "".join(parts).strip()
        if joined:
            return joined

    extra = getattr(response, "additional_kwargs", {}) or {}
    for key in ("text", "reasoning_content"):
        value = extra.get(key)
        if value:
            return str(value).strip()

    return ""
