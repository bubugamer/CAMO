from __future__ import annotations

from pathlib import Path

import pytest

from camo.core.settings import get_settings


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434/v1")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://camo:test@localhost:5432/camo")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATA_ROOT", str((root / "data").resolve()))
    monkeypatch.setenv("MODEL_CONFIG_PATH", str((root / "config/models.yaml").resolve()))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
