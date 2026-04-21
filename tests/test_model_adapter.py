from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from camo.models.adapter import CompletionResult, EmbeddingResult, ModelAdapter, UnknownProviderError
from camo.models.structured import StructuredOutputError
from camo.models.config import load_model_routing_config


class FakeProvider:
    def __init__(self) -> None:
        self.complete_calls: list[dict[str, Any]] = []
        self.embed_calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        route,
        messages,
        json_schema,
        temperature,
        max_tokens,
    ) -> CompletionResult:
        self.complete_calls.append(
            {
                "route": route,
                "messages": messages,
                "json_schema": json_schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return CompletionResult(
            content="ok",
            structured={"status": "ok"},
            usage={"input_tokens": 10, "output_tokens": 2},
            model=route.model,
            latency_ms=12,
        )

    async def embed(self, *, route, texts) -> EmbeddingResult:
        self.embed_calls.append({"route": route, "texts": texts})
        return EmbeddingResult(vectors=[[0.1, 0.2, 0.3]], model=route.model, dimensions=3)


class RepairingProvider:
    def __init__(self) -> None:
        self.complete_calls: list[list[dict[str, Any]]] = []

    async def complete(
        self,
        *,
        route,
        messages,
        json_schema,
        temperature,
        max_tokens,
    ) -> CompletionResult:
        self.complete_calls.append(messages)
        if len(self.complete_calls) == 1:
            raise StructuredOutputError(
                "Model JSON did not match the requested schema",
                raw_data={"status": 1},
                validation_message="1 is not of type 'string'",
            )
        return CompletionResult(
            content='{"status":"ok"}',
            structured={"status": "ok"},
            usage={"input_tokens": 8, "output_tokens": 2},
            model=route.model,
            latency_ms=5,
        )

    async def embed(self, *, route, texts) -> EmbeddingResult:
        raise NotImplementedError


def test_model_adapter_routes_completion_calls() -> None:
    config = load_model_routing_config(Path("config/models.yaml"))
    openai_provider = FakeProvider()
    adapter = ModelAdapter(config, providers={"openai": openai_provider})

    result = asyncio.run(
        adapter.complete(
            messages=[{"role": "user", "content": "hello"}],
            task="runtime",
            json_schema={"type": "object"},
        )
    )

    assert result.model == "moonshot-v1-32k"
    assert openai_provider.complete_calls[0]["temperature"] == 0.0
    assert openai_provider.complete_calls[0]["max_tokens"] == 4096


def test_model_adapter_routes_embedding_calls() -> None:
    config = load_model_routing_config(Path("config/models.yaml"))
    ollama_provider = FakeProvider()
    adapter = ModelAdapter(config, providers={"ollama": ollama_provider})

    result = asyncio.run(adapter.embed(["memory one", "memory two"]))

    assert result.model == "nomic-embed-text"
    assert ollama_provider.embed_calls[0]["texts"] == ["memory one", "memory two"]


def test_model_adapter_raises_for_unregistered_provider() -> None:
    config = load_model_routing_config(Path("config/models.yaml"))
    adapter = ModelAdapter(config)

    with pytest.raises(UnknownProviderError):
        asyncio.run(adapter.complete(messages=[{"role": "user", "content": "hi"}], task="runtime"))


def test_model_adapter_retries_with_schema_repair_message() -> None:
    config = load_model_routing_config(Path("config/models.yaml"))
    provider = RepairingProvider()
    adapter = ModelAdapter(config, providers={"openai": provider}, max_retries=2)

    result = asyncio.run(
        adapter.complete(
            messages=[{"role": "user", "content": "return status"}],
            task="runtime",
            json_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["status"],
                "properties": {
                    "status": {"type": "string"},
                },
            },
        )
    )

    assert result.structured == {"status": "ok"}
    assert len(provider.complete_calls) == 2
    retry_messages = provider.complete_calls[1]
    assert retry_messages[-2]["role"] == "assistant"
    assert retry_messages[-2]["content"] == '{"status": 1}'
    assert retry_messages[-1]["role"] == "user"
    assert "没有通过结构化校验" in retry_messages[-1]["content"]
