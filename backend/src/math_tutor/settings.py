from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from math_tutor.generation import DEMO_INFERENCE_MODEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    nebius_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    nebius_model: str = DEMO_INFERENCE_MODEL
    elevenlabs_voice_id: str = "Xb7hH8MSUJpSbSDYk0k2"
    artifact_root: Path = Path("artifacts")
    render_timeout_seconds: float = Field(default=90, gt=0)
    max_pending_jobs: int = Field(default=8, gt=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
