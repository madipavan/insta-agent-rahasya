"""Dynamic LLM provider abstraction."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from src.config import AppConfig
from src.utils.json_parse import parse_llm_json


class ScriptProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 2048) -> str:
        ...

    def complete_json(self, prompt: str, max_tokens: int = 2048) -> dict[str, Any]:
        raw = self.complete(prompt, max_tokens=max_tokens)
        return parse_llm_json(raw)


class AnthropicProvider(ScriptProvider):
    def __init__(self, config: AppConfig) -> None:
        from anthropic import Anthropic

        if not config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.model = config.llm_model_anthropic

    def complete(self, prompt: str, max_tokens: int = 2048) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


class OpenAIProvider(ScriptProvider):
    def __init__(self, config: AppConfig) -> None:
        from openai import OpenAI

        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.llm_model_openai

    def complete(self, prompt: str, max_tokens: int = 2048) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


class GroqProvider(ScriptProvider):
    """Groq free-tier API (OpenAI-compatible)."""

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, config: AppConfig) -> None:
        from openai import OpenAI

        if not config.groq_api_key:
            raise ValueError("GROQ_API_KEY not set")
        self.client = OpenAI(api_key=config.groq_api_key, base_url=self.BASE_URL)
        self.model = config.llm_model_groq

    def complete(self, prompt: str, max_tokens: int = 8192) -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if _groq_uses_reasoning(self.model):
            kwargs["reasoning_format"] = "hidden"
            kwargs["reasoning_effort"] = "low"
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""


def _groq_uses_reasoning(model: str) -> bool:
    name = model.lower()
    return "gpt-oss" in name or "qwen" in name or name.startswith("groq/compound")


class GeminiProvider(ScriptProvider):
    """Google Gemini API (free tier via AI Studio)."""

    def __init__(self, config: AppConfig) -> None:
        from google import genai

        if not config.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=config.gemini_api_key)
        self.model = config.llm_model_gemini

    def complete(self, prompt: str, max_tokens: int = 8192) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={"max_output_tokens": max_tokens, "temperature": 0.7},
        )
        return response.text or ""


def get_provider(config: AppConfig) -> ScriptProvider:
    provider = config.llm_provider.lower()
    if provider == "openai":
        return OpenAIProvider(config)
    if provider == "groq":
        return GroqProvider(config)
    if provider == "gemini":
        return GeminiProvider(config)
    return AnthropicProvider(config)

