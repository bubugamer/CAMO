from __future__ import annotations

from pathlib import Path

import pytest

from camo.core.settings import Settings
from camo.models.config import ModelConfigError, load_model_routing_config


def test_model_config_loads_and_expands_environment_variables() -> None:
    config = load_model_routing_config(Path("config/models.yaml"), env=Settings().model_env())

    extraction = config.resolve("extraction")
    embedding = config.resolve("embedding")

    assert extraction.provider == "openai"
    assert config.providers["anthropic"]["api_key"] == "test-anthropic-key"
    assert extraction.provider_config["api_key"] == "test-openai-key"
    assert extraction.provider_config["base_url"] == "https://api.openai.com/v1"
    assert extraction.temperature == 0.0
    assert extraction.max_tokens == 4096
    assert embedding.provider == "ollama"
    assert embedding.provider_config["base_url"] == "http://ollama.test:11434/v1"
    assert config.providers["openai"]["base_url"] == "https://api.openai.com/v1"


def test_model_config_raises_for_unknown_task() -> None:
    config = load_model_routing_config(Path("config/models.yaml"))

    with pytest.raises(ModelConfigError):
        config.resolve("missing-task")
