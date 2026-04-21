from __future__ import annotations

from pathlib import Path

from camo.core.settings import Settings


def test_settings_load_database_and_model_paths() -> None:
    settings = Settings()

    assert settings.database_url == "postgresql+asyncpg://camo:test@localhost:5432/camo"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.data_root == Path("data").resolve()
    assert settings.model_config_path == Path("config/models.yaml").resolve()
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.ollama_base_url == "http://ollama.test:11434/v1"
