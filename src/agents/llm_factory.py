"""LangChain LLM factory for CrewAI and LangGraph."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from src.config import AppConfig


def _groq_uses_reasoning(model: str) -> bool:
    name = model.lower()
    return "gpt-oss" in name or "qwen" in name or name.startswith("groq/compound")


def get_chat_model(config: AppConfig, temperature: float = 0.7) -> BaseChatModel:
    provider = config.llm_provider.lower()

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
        # Reasoning models (gpt-oss, qwen) otherwise return empty content on long prompts.
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
            # Gemini 2.5 Flash spends tokens on thinking by default, which can
            # leave JSON output empty when the editor rewrites a long draft.
            thinking_budget=0,
            response_mime_type="application/json",
        )

    from langchain_anthropic import ChatAnthropic

    if not config.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    return ChatAnthropic(
        model=config.llm_model_anthropic,
        api_key=config.anthropic_api_key,
        temperature=temperature,
    )
