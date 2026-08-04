"""Multi-provider LLM fallback — switch on quota / rate-limit errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.agents.llm_factory import build_chat_model, provider_chain
from src.utils.llm_errors import is_llm_limit_error

if TYPE_CHECKING:
    from src.config import AppConfig
    from src.pipeline.logger import PipelineLogger


class FallbackChatModel:
    """Thin wrapper: tries providers in order, sticks with the last working one."""

    def __init__(
        self,
        config: AppConfig,
        temperature: float,
        logger: PipelineLogger | None = None,
    ) -> None:
        self.config = config
        self.temperature = temperature
        self.logger = logger
        self._chain = provider_chain(config)
        self._active_idx = 0

    def invoke(self, messages: list[Any]) -> Any:
        if not self._chain:
            raise ValueError("No LLM providers configured (set API keys in secrets / .env)")

        last_exc: Exception | None = None
        for idx in range(self._active_idx, len(self._chain)):
            provider = self._chain[idx]
            llm = build_chat_model(self.config, provider, self.temperature)
            try:
                result = llm.invoke(messages)
                self._active_idx = idx
                return result
            except Exception as exc:
                last_exc = exc
                if is_llm_limit_error(exc) and idx < len(self._chain) - 1:
                    nxt = self._chain[idx + 1]
                    if self.logger:
                        self.logger.warn(
                            "llm",
                            f"{provider} limit hit — switching to {nxt}",
                        )
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("LLM invoke failed with no providers")
