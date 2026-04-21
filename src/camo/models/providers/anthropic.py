from __future__ import annotations

import json
import time
from typing import Any

from anthropic import AsyncAnthropic

from camo.models.adapter import CompletionResult, EmbeddingResult
from camo.models.structured import parse_and_validate_json, validate_structured_payload


class AnthropicProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "max_retries": 0,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncAnthropic(**client_kwargs)

    async def complete(
        self,
        *,
        route,
        messages,
        json_schema,
        temperature,
        max_tokens,
    ) -> CompletionResult:
        system_text, anthropic_messages = _split_system_message(messages)
        request_kwargs: dict[str, Any] = {
            "model": route.model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            request_kwargs["system"] = system_text
        if json_schema is not None:
            request_kwargs["tools"] = [
                {
                    "name": "emit_structured_output",
                    "description": "Return the structured result for this task.",
                    "input_schema": json_schema,
                }
            ]
            request_kwargs["tool_choice"] = {
                "type": "tool",
                "name": "emit_structured_output",
            }

        started = time.perf_counter()
        message = await self._client.messages.create(**request_kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)

        text_parts: list[str] = []
        structured: dict[str, Any] | None = None
        for block in message.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", ""))
            elif block_type == "tool_use":
                tool_input = getattr(block, "input", None)
                if isinstance(tool_input, dict):
                    structured = (
                        validate_structured_payload(tool_input, json_schema)
                        if json_schema is not None
                        else tool_input
                    )

        content = "\n".join(part for part in text_parts if part).strip()
        if json_schema is not None and structured is None:
            structured = parse_and_validate_json(content, json_schema)
        if json_schema is not None and not content and structured is not None:
            content = json.dumps(structured, ensure_ascii=False)

        return CompletionResult(
            content=content,
            structured=structured,
            usage={
                "input_tokens": getattr(message.usage, "input_tokens", 0),
                "output_tokens": getattr(message.usage, "output_tokens", 0),
            },
            model=getattr(message, "model", route.model),
            latency_ms=latency_ms,
        )

    async def embed(self, *, route, texts) -> EmbeddingResult:
        raise NotImplementedError("Anthropic does not provide embeddings in this adapter")

    async def aclose(self) -> None:
        await self._client.close()


def _split_system_message(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, str]]]:
    system_parts: list[str] = []
    anthropic_messages: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role", "user")
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
        else:
            anthropic_messages.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": content,
                }
            )
    system_text = "\n\n".join(part for part in system_parts if part) or None
    return system_text, anthropic_messages
