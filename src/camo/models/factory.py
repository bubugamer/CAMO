from __future__ import annotations

from camo.models.adapter import ModelAdapter, ProviderConfigurationError
from camo.models.config import ModelRoutingConfig
from camo.models.providers.anthropic import AnthropicProvider
from camo.models.providers.openai_compat import OpenAICompatibleProvider


class UnavailableProvider:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def complete(self, **_: object) -> object:
        raise ProviderConfigurationError(self._reason)

    async def embed(self, **_: object) -> object:
        raise ProviderConfigurationError(self._reason)

    async def aclose(self) -> None:
        return None


def build_provider_registry(routing_config: ModelRoutingConfig) -> dict[str, object]:
    providers: dict[str, object] = {}

    for name, provider_config in routing_config.providers.items():
        if name == "anthropic":
            api_key = provider_config.get("api_key")
            if not api_key:
                providers[name] = UnavailableProvider(
                    "Anthropic provider is not configured. Set ANTHROPIC_API_KEY."
                )
            else:
                providers[name] = AnthropicProvider(
                    api_key=api_key,
                    base_url=provider_config.get("base_url"),
                )
        elif name in {"openai", "ollama"}:
            api_key = provider_config.get("api_key")
            base_url = provider_config.get("base_url")
            if name == "openai" and not api_key:
                providers[name] = UnavailableProvider(
                    "OpenAI-compatible provider is not configured. Set OPENAI_API_KEY."
                )
            elif not base_url and name == "ollama":
                providers[name] = UnavailableProvider(
                    "Ollama provider is not configured. Set OLLAMA_BASE_URL."
                )
            else:
                providers[name] = OpenAICompatibleProvider(
                    api_key=api_key or "ollama",
                    base_url=base_url,
                )
        else:
            providers[name] = UnavailableProvider(f"Unsupported provider '{name}'.")

    return providers
