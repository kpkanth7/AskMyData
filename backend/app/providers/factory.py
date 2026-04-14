from __future__ import annotations

from typing import Any, Dict

from app.config.settings import Settings
from app.providers.base import LLMProvider
from app.providers.cerebras import CerebrasProvider
from app.providers.ollama import OllamaProvider


class ProviderRouter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.providers: list[LLMProvider] = []
        primary = self._build_provider(settings.default_llm_provider, settings.default_llm_model, is_fallback=False)
        if primary is not None:
            self.providers.append(primary)
        fallback = self._build_provider(settings.fallback_llm_provider, settings.fallback_llm_model, is_fallback=True)
        if fallback is not None and fallback.name not in {provider.name for provider in self.providers}:
            self.providers.append(fallback)

    @property
    def available(self) -> bool:
        return bool(self.providers)

    async def structured_json(self, system_prompt: str, user_prompt: str, schema_hint: Dict[str, Any]) -> Dict[str, Any]:
        return await self._with_fallback("structured_json", system_prompt, user_prompt, schema_hint)

    async def text(self, system_prompt: str, user_prompt: str, temperature: float = 0.25) -> str:
        return await self._with_fallback("text", system_prompt, user_prompt, temperature)

    async def _with_fallback(self, method: str, *args: Any) -> Any:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return await getattr(provider, method)(*args)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("No LLM provider is configured")

    def _build_provider(self, provider_name: str, model: str, is_fallback: bool) -> LLMProvider | None:
        name = provider_name.strip().lower()
        if name == "ollama":
            if is_fallback and not self.settings.enable_llm_fallback:
                return None
            return OllamaProvider(
                base_url=self.settings.ollama_base_url,
                model=self.settings.ollama_model or model or self.settings.fallback_llm_model,
                timeout_seconds=self.settings.ollama_timeout_seconds,
            )
        if not self.settings.cerebras_api_key:
            return None
        return CerebrasProvider(
            api_key=self.settings.cerebras_api_key,
            base_url=self.settings.cerebras_base_url,
            model=self.settings.cerebras_model or model or self.settings.default_llm_model,
        )
