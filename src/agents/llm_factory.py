"""LangChain LLM factory for CrewAI and LangGraph."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from src.config import AppConfig


def get_chat_model(config: AppConfig, temperature: float = 0.7) -> BaseChatModel:
    provider = config.llm_provider.lower()

    if provider == "groq":
        from langchain_groq import ChatGroq

        if not config.groq_api_key:
            raise ValueError("GROQ_API_KEY not set")
        return ChatGroq(
            model=config.llm_model_groq,
            api_key=config.groq_api_key,
            temperature=temperature,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return ChatOpenAI(
            model=config.llm_model_openai,
            api_key=config.openai_api_key,
            temperature=temperature,
        )

    from langchain_anthropic import ChatAnthropic

    if not config.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    return ChatAnthropic(
        model=config.llm_model_anthropic,
        api_key=config.anthropic_api_key,
        temperature=temperature,
    )
