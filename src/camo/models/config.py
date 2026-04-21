from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ModelConfigError(ValueError):
    """Raised when the model routing config is invalid."""


@dataclass(frozen=True)
class RoutingDefaults:
    temperature: float = 0.0
    max_tokens: int = 4096


@dataclass(frozen=True)
class ResolvedRoute:
    task: str
    provider: str
    model: str
    provider_config: dict[str, Any]
    temperature: float
    max_tokens: int
    fallback: str | None = None


@dataclass(frozen=True)
class ModelRoutingConfig:
    providers: dict[str, dict[str, Any]]
    routing: dict[str, dict[str, Any]]
    defaults: RoutingDefaults

    def list_tasks(self) -> list[str]:
        return sorted(self.routing)

    def resolve(self, task: str) -> ResolvedRoute:
        route = self.routing.get(task)
        if route is None:
            raise ModelConfigError(f"Unknown routing task: {task}")

        provider_name = route.get("provider")
        if not provider_name:
            raise ModelConfigError(f"Routing task '{task}' is missing a provider")

        provider_config = self.providers.get(provider_name)
        if provider_config is None:
            raise ModelConfigError(
                f"Routing task '{task}' references unknown provider '{provider_name}'"
            )

        model_name = route.get("model")
        if not model_name:
            raise ModelConfigError(f"Routing task '{task}' is missing a model")

        return ResolvedRoute(
            task=task,
            provider=provider_name,
            model=model_name,
            provider_config=_sanitize_mapping(provider_config),
            temperature=float(route.get("temperature", self.defaults.temperature)),
            max_tokens=int(route.get("max_tokens", self.defaults.max_tokens)),
            fallback=route.get("fallback"),
        )


def load_model_routing_config(
    path: str | Path,
    *,
    env: dict[str, str] | None = None,
) -> ModelRoutingConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ModelConfigError(f"Model config file does not exist: {config_path}")

    raw_data = yaml.safe_load(
        _expand_env_values(config_path.read_text(encoding="utf-8"), env=env)
    )
    if not isinstance(raw_data, dict):
        raise ModelConfigError("Model config must be a mapping")

    providers = raw_data.get("providers")
    routing = raw_data.get("routing")
    if not isinstance(providers, dict) or not providers:
        raise ModelConfigError("Model config must define at least one provider")
    if not isinstance(routing, dict) or not routing:
        raise ModelConfigError("Model config must define at least one routing entry")

    defaults_raw = raw_data.get("defaults") or {}
    if not isinstance(defaults_raw, dict):
        raise ModelConfigError("Model config defaults must be a mapping")

    defaults = RoutingDefaults(
        temperature=float(defaults_raw.get("temperature", 0.0)),
        max_tokens=int(defaults_raw.get("max_tokens", 4096)),
    )

    normalized_providers = {
        name: _sanitize_mapping(_ensure_mapping(config, f"provider '{name}'"))
        for name, config in providers.items()
    }
    normalized_routing = {
        task: _sanitize_mapping(_ensure_mapping(config, f"routing task '{task}'"))
        for task, config in routing.items()
    }

    return ModelRoutingConfig(
        providers=normalized_providers,
        routing=normalized_routing,
        defaults=defaults,
    )


def _ensure_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelConfigError(f"{label} must be a mapping")
    return dict(value)


def _sanitize_mapping(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if value in ("", None):
            continue
        sanitized[key] = value
    return sanitized


def _expand_env_values(content: str, *, env: dict[str, str] | None = None) -> str:
    env_values = env or {}
    return ENV_PATTERN.sub(
        lambda match: env_values.get(match.group(1), os.getenv(match.group(1), "")),
        content,
    )
