from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable, Protocol

from camo.models.config import ModelRoutingConfig, ResolvedRoute
from camo.models.structured import StructuredOutputError, parse_and_validate_json, validate_structured_payload


@dataclass(frozen=True)
class CompletionResult:
    content: str
    structured: dict[str, Any] | None
    usage: dict[str, int]
    model: str
    latency_ms: int


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimensions: int


@dataclass(frozen=True)
class LLMCallLogEntry:
    task: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    status: str
    error_message: str | None = None


class Provider(Protocol):
    async def complete(
        self,
        *,
        route: ResolvedRoute,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> CompletionResult: ...

    async def embed(
        self,
        *,
        route: ResolvedRoute,
        texts: list[str],
    ) -> EmbeddingResult: ...

    async def aclose(self) -> None: ...


class UnknownProviderError(LookupError):
    """Raised when the routing layer resolves to a provider without an implementation."""


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider exists in config but lacks required runtime credentials."""


class ModelAdapter:
    def __init__(
        self,
        routing_config: ModelRoutingConfig,
        providers: dict[str, Provider] | None = None,
        log_callback: Callable[[LLMCallLogEntry], Awaitable[None]] | None = None,
        max_retries: int = 3,
    ) -> None:
        self._routing_config = routing_config
        self._providers = providers or {}
        self._log_callback = log_callback
        self._max_retries = max_retries

    def register_provider(self, name: str, provider: Provider) -> None:
        self._providers[name] = provider

    async def complete(
        self,
        messages: list[dict[str, Any]],
        task: str = "default",
        json_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        route = self._routing_config.resolve(task)
        return await self._complete_with_route(
            route=route,
            messages=messages,
            json_schema=json_schema,
            temperature=route.temperature if temperature is None else temperature,
            max_tokens=route.max_tokens if max_tokens is None else max_tokens,
        )

    async def embed(
        self,
        texts: list[str],
        task: str = "embedding",
    ) -> EmbeddingResult:
        route = self._routing_config.resolve(task)
        provider = self._get_provider(route.provider)
        return await provider.embed(route=route, texts=texts)

    async def aclose(self) -> None:
        for provider in self._providers.values():
            aclose = getattr(provider, "aclose", None)
            if aclose is not None:
                await aclose()

    def _get_provider(self, name: str) -> Provider:
        provider = self._providers.get(name)
        if provider is None:
            raise UnknownProviderError(f"No provider registered for '{name}'")
        return provider

    async def _complete_with_route(
        self,
        *,
        route: ResolvedRoute,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> CompletionResult:
        provider = self._get_provider(route.provider)
        error: Exception | None = None
        attempt_messages = list(messages)

        for attempt in range(1, self._max_retries + 1):
            try:
                result = await provider.complete(
                    route=route,
                    messages=attempt_messages,
                    json_schema=json_schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if json_schema is not None:
                    result = self._normalize_structured_result(result, json_schema)
                await self._emit_log(
                    LLMCallLogEntry(
                        task=route.task,
                        provider=route.provider,
                        model=result.model,
                        input_tokens=result.usage.get("input_tokens"),
                        output_tokens=result.usage.get("output_tokens"),
                        latency_ms=result.latency_ms,
                        status="success",
                    )
                )
                return result
            except StructuredOutputError as exc:
                error = exc
                await self._emit_log(
                    LLMCallLogEntry(
                        task=route.task,
                        provider=route.provider,
                        model=route.model,
                        input_tokens=None,
                        output_tokens=None,
                        latency_ms=None,
                        status="error",
                        error_message=self._format_structured_error(exc),
                    )
                )
                if attempt < self._max_retries:
                    attempt_messages = self._build_schema_repair_messages(
                        original_messages=messages,
                        json_schema=json_schema,
                        error=exc,
                    )
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
            except Exception as exc:
                error = exc
                await self._emit_log(
                    LLMCallLogEntry(
                        task=route.task,
                        provider=route.provider,
                        model=route.model,
                        input_tokens=None,
                        output_tokens=None,
                        latency_ms=None,
                        status="error",
                        error_message=str(exc),
                    )
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

        if route.fallback:
            fallback_route = self._routing_config.resolve(route.fallback)
            return await self._complete_with_route(
                route=fallback_route,
                messages=messages,
                json_schema=json_schema,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        assert error is not None
        raise error

    def _normalize_structured_result(
        self,
        result: CompletionResult,
        json_schema: dict[str, Any],
    ) -> CompletionResult:
        if result.structured is not None:
            structured = validate_structured_payload(
                result.structured,
                json_schema,
                raw_text=result.content,
            )
            return replace(result, structured=structured)

        structured = parse_and_validate_json(result.content, json_schema)
        normalized_content = result.content or json.dumps(structured, ensure_ascii=False)
        return replace(result, content=normalized_content, structured=structured)

    def _build_schema_repair_messages(
        self,
        *,
        original_messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None,
        error: StructuredOutputError,
    ) -> list[dict[str, Any]]:
        assert json_schema is not None
        repaired_messages = list(original_messages)
        previous_output = self._extract_error_payload(error)
        if previous_output:
            repaired_messages.append({"role": "assistant", "content": previous_output})

        repaired_messages.append(
            {
                "role": "user",
                "content": (
                    "你上一条回复没有通过结构化校验。"
                    f"错误原因：{self._format_structured_error(error)}。\n"
                    "请修正为一个严格合法的 JSON 对象，不要输出解释、不要输出 Markdown、不要输出代码块。\n"
                    f"必须完全匹配这个 JSON Schema：{json.dumps(json_schema, ensure_ascii=False)}"
                ),
            }
        )
        return repaired_messages

    def _extract_error_payload(self, error: StructuredOutputError) -> str:
        if error.raw_text:
            return error.raw_text
        if error.raw_data is not None:
            try:
                return json.dumps(error.raw_data, ensure_ascii=False)
            except TypeError:
                return str(error.raw_data)
        return ""

    def _format_structured_error(self, error: StructuredOutputError) -> str:
        if error.validation_message:
            return f"{error}. Validation detail: {error.validation_message}"
        return str(error)

    async def _emit_log(self, entry: LLMCallLogEntry) -> None:
        if self._log_callback is not None:
            await self._log_callback(entry)
