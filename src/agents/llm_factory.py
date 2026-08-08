"""LangChain LLM factory for CrewAI and LangGraph."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from src.config import AppConfig


def _groq_uses_reasoning(model: str) -> bool:
    name = model.lower()
    return "gpt-oss" in name or "qwen" in name or name.startswith("groq/compound")


def _has_api_key(config: AppConfig, provider: str) -> bool:
    keys = {
        "grok": config.grok_api_key,
        "groq": config.groq_api_key,
        "gemini": config.gemini_api_key,
        "mistral": config.mistral_api_key,
        "openai": config.openai_api_key,
        "anthropic": config.anthropic_api_key,
    }
    return bool(keys.get(provider, ""))


def provider_chain(config: AppConfig) -> list[str]:
    """Ordered providers to try (primary + fallbacks, only those with API keys)."""
    primary = config.llm_provider.lower()
    fallbacks = [p.lower() for p in config.llm_fallback_providers]
    chain: list[str] = []
    for name in [primary, *fallbacks]:
        if name in chain:
            continue
        if _has_api_key(config, name):
            chain.append(name)
    return chain


def build_chat_model(
    config: AppConfig,
    provider: str,
    temperature: float = 0.7,
) -> BaseChatModel:
    provider = provider.lower()

    if provider == "grok":
        from langchain_openai import ChatOpenAI

        if not config.grok_api_key:
            raise ValueError("GROK_API_KEY not set")
        return ChatOpenAI(
            model=config.llm_model_grok,
            api_key=config.grok_api_key,
            base_url="https://api.x.ai/v1",
            temperature=temperature,
            max_tokens=8192,
        )

    if provider == "groq":
        from langchain_groq import ChatGroq

        if not config.groq_api_key:
            raise ValueError("GROQ_API_KEY not set")
        groq_kwargs: dict = {
            "model": config.llm_model_groq,
            "api_key": config.groq_api_key,
            "temperature": temperature,
            "max_tokens": 8192,
        }
        if _groq_uses_reasoning(config.llm_model_groq):
            groq_kwargs["reasoning_format"] = "hidden"
            groq_kwargs["reasoning_effort"] = "low"
        return ChatGroq(**groq_kwargs)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return ChatOpenAI(
            model=config.llm_model_openai,
            api_key=config.openai_api_key,
            temperature=temperature,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not config.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set")
        return ChatGoogleGenerativeAI(
            model=config.llm_model_gemini,
            google_api_key=config.gemini_api_key,
            temperature=temperature,
            max_output_tokens=8192,
            thinking_budget=0,
            response_mime_type="application/json",
        )

    if provider == "mistral":
        from langchain_openai import ChatOpenAI

        if not config.mistral_api_key:
            raise ValueError("MISTRAL_API_KEY not set")
        # OpenAI-compatible API — avoids langchain-mistralai / httpx_sse import bugs on CI.
        return ChatOpenAI(
            model=config.llm_model_mistral,
            api_key=config.mistral_api_key,
            base_url="https://api.mistral.ai/v1",
            temperature=temperature,
            max_tokens=8192,
        )

    from langchain_anthropic import ChatAnthropic

    if not config.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    return ChatAnthropic(
        model=config.llm_model_anthropic,
        api_key=config.anthropic_api_key,
        temperature=temperature,
    )


def get_chat_model(
    config: AppConfig,
    temperature: float = 0.7,
    logger=None,
) -> BaseChatModel | object:
    chain = provider_chain(config)
    if len(chain) > 1:
        from src.agents.llm_fallback import FallbackChatModel

        return FallbackChatModel(config, temperature, logger)
    if not chain:
        raise ValueError(
            "No LLM API keys set. Add GROK_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, or MISTRAL_API_KEY."
        )
    return build_chat_model(config, chain[0], temperature)
