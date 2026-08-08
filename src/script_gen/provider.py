"""Dynamic LLM provider abstraction."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from src.config import AppConfig
from src.utils.json_parse import parse_llm_json
from src.utils.llm_errors import is_llm_limit_error
from src.agents.llm_factory import provider_chain


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


class GrokProvider(ScriptProvider):
    """xAI Grok API (OpenAI-compatible)."""

    BASE_URL = "https://api.x.ai/v1"

    def __init__(self, config: AppConfig) -> None:
        from openai import OpenAI

        if not config.grok_api_key:
            raise ValueError("GROK_API_KEY not set")
        self.client = OpenAI(api_key=config.grok_api_key, base_url=self.BASE_URL)
        self.model = config.llm_model_grok

    def complete(self, prompt: str, max_tokens: int = 8192) -> str:
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
        from google.genai import types

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=0.7,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
            ),
        )
        return response.text or ""


class MistralProvider(ScriptProvider):
    """Mistral AI API (OpenAI-compatible)."""

    BASE_URL = "https://api.mistral.ai/v1"

    def __init__(self, config: AppConfig) -> None:
        from openai import OpenAI

        if not config.mistral_api_key:
            raise ValueError("MISTRAL_API_KEY not set")
        self.client = OpenAI(api_key=config.mistral_api_key, base_url=self.BASE_URL)
        self.model = config.llm_model_mistral

    def complete(self, prompt: str, max_tokens: int = 8192) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


def _build_provider(config: AppConfig, provider: str) -> ScriptProvider:
    provider = provider.lower()
    if provider == "openai":
        return OpenAIProvider(config)
    if provider == "grok":
        return GrokProvider(config)
    if provider == "groq":
        return GroqProvider(config)
    if provider == "gemini":
        return GeminiProvider(config)
    if provider == "mistral":
        return MistralProvider(config)
    return AnthropicProvider(config)


class FallbackScriptProvider(ScriptProvider):
    """Tries providers in order on quota / rate-limit errors."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._chain = provider_chain(config)
        self._active_idx = 0

    def complete(self, prompt: str, max_tokens: int = 2048) -> str:
        if not self._chain:
            raise ValueError("No LLM API keys configured")

        last_exc: Exception | None = None
        for idx in range(self._active_idx, len(self._chain)):
            provider = self._chain[idx]
            client = _build_provider(self.config, provider)
            try:
                text = client.complete(prompt, max_tokens=max_tokens)
                self._active_idx = idx
                return text
            except Exception as exc:
                last_exc = exc
                if is_llm_limit_error(exc) and idx < len(self._chain) - 1:
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("LLM complete failed")


def get_provider(config: AppConfig) -> ScriptProvider:
    chain = provider_chain(config)
    if len(chain) > 1:
        return FallbackScriptProvider(config)
    if not chain:
        raise ValueError("No LLM API keys configured")
    return _build_provider(config, chain[0])

