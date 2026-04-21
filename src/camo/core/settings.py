from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="CAMO API", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    database_url: str = Field(
        default="postgresql+asyncpg://camo:changeme@localhost:5432/camo",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_base_url: str | None = Field(default=None, alias="ANTHROPIC_BASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(
        default="https://api.openai.com/v1",
        alias="OPENAI_BASE_URL",
    )
    ollama_base_url: str | None = Field(
        default="http://localhost:11434/v1",
        alias="OLLAMA_BASE_URL",
    )
    data_root: Path = Field(default=Path("data"), alias="DATA_ROOT")
    model_config_path: Path = Field(
        default=Path("config/models.yaml"),
        alias="MODEL_CONFIG_PATH",
    )

    @model_validator(mode="after")
    def resolve_paths(self) -> Settings:
        self.model_config_path = self._resolve_path(self.model_config_path)
        self.data_root = self._resolve_path(self.data_root)
        return self

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        resolved = path.expanduser()
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()
        return resolved

    def model_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key, value in {
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "ANTHROPIC_BASE_URL": self.anthropic_base_url,
            "OPENAI_API_KEY": self.openai_api_key,
            "OPENAI_BASE_URL": self.openai_base_url,
            "OLLAMA_BASE_URL": self.ollama_base_url,
        }.items():
            if value:
                env[key] = value
        return env


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
