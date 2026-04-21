from __future__ import annotations

import json
import time
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from camo.models.adapter import CompletionResult, EmbeddingResult
from camo.models.structured import parse_and_validate_json


class OpenAICompatibleProvider:
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
        self._client = AsyncOpenAI(**client_kwargs)

    async def complete(
        self,
        *,
        route,
        messages,
        json_schema,
        temperature,
        max_tokens,
    ) -> CompletionResult:
        started = time.perf_counter()
        request_messages = messages
        request_kwargs: dict[str, Any] = {
            "model": route.model,
            "messages": request_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_schema is not None and route.provider == "openai":
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": json_schema,
                },
            }

        try:
            response = await self._client.chat.completions.create(**request_kwargs)
        except BadRequestError:
            if json_schema is None:
                raise
            fallback_messages = _with_json_instruction(messages, json_schema)
            response = await self._client.chat.completions.create(
                model=route.model,
                messages=fallback_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = response.choices[0].message
        content = choice.content or ""

        structured: dict[str, Any] | None = None
        if json_schema is not None:
            structured = parse_and_validate_json(content, json_schema)

        return CompletionResult(
            content=content,
            structured=structured,
            usage={
                "input_tokens": getattr(response.usage, "prompt_tokens", 0),
                "output_tokens": getattr(response.usage, "completion_tokens", 0),
            },
            model=getattr(response, "model", route.model),
            latency_ms=latency_ms,
        )

    async def embed(self, *, route, texts) -> EmbeddingResult:
        response = await self._client.embeddings.create(model=route.model, input=texts)
        vectors = [item.embedding for item in response.data]
        dimensions = len(vectors[0]) if vectors else 0
        return EmbeddingResult(vectors=vectors, model=route.model, dimensions=dimensions)

    async def aclose(self) -> None:
        await self._client.close()


def _with_json_instruction(
    messages: list[dict[str, Any]],
    json_schema: dict[str, Any],
) -> list[dict[str, str]]:
    instruction = (
        "Return only valid JSON that matches this schema exactly.\n"
        f"{json.dumps(json_schema, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": instruction}] + [
        {"role": str(message.get("role", "user")), "content": str(message.get("content", ""))}
        for message in messages
    ]
