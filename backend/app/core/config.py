"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Repository root = parents[3] (core -> app -> backend -> repo)
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """All runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────────
    backend_host: str = Field(default="0.0.0.0", alias="BACKEND_HOST")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ── OpenMRS ──────────────────────────────────────────────────────────
    openmrs_base_url: str = Field(
        default="http://localhost:8080/openmrs", alias="OPENMRS_BASE_URL"
    )
    openmrs_fhir_url: str = Field(
        default="http://localhost:8080/openmrs/ws/fhir2/R4",
        alias="OPENMRS_FHIR_URL",
    )
    openmrs_api_user: str = Field(default="admin", alias="OPENMRS_API_USER")
    openmrs_api_password: str = Field(
        default="Admin123", alias="OPENMRS_API_PASSWORD"
    )

    # ── LLM provider switch ──────────────────────────────────────────────
    llm_provider: Literal["openrouter", "azure"] = Field(
        default="openrouter", alias="LLM_PROVIDER"
    )

    # ── OpenRouter ───────────────────────────────────────────────────────
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(
        default="moonshotai/kimi-k2.6", alias="OPENROUTER_MODEL"
    )

    # ── Azure OpenAI ─────────────────────────────────────────────────────
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = Field(
        default="2024-10-21", alias="AZURE_OPENAI_API_VERSION"
    )
    azure_openai_deployment: str = Field(
        default="", alias="AZURE_OPENAI_DEPLOYMENT"
    )

    # ── Langfuse ─────────────────────────────────────────────────────────
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="http://localhost:3100", alias="LANGFUSE_HOST"
    )

    # ── Data ─────────────────────────────────────────────────────────────
    id_map_path: Path = Field(
        default=_REPO_ROOT / "data" / "fixtures" / "id_map.json",
        alias="ID_MAP_PATH",
    )

    # ── Agent defaults ───────────────────────────────────────────────────
    # Default look-back window when the supervisor does not specify a range.
    # The seeded encounter data may not always include "today", so this is
    # configurable per environment.
    briefing_default_lookback_days: int = Field(
        default=30, alias="BRIEFING_DEFAULT_LOOKBACK_DAYS", ge=1, le=365
    )

    # ── LLM retry (mirrors the FHIR client pattern) ──────────────────────
    # Transport errors and 5xx responses are retried with exponential backoff.
    # 4xx (including 429 — see follow-up task) are surfaced immediately.
    llm_max_attempts: int = Field(
        default=3, alias="LLM_MAX_ATTEMPTS", ge=1, le=10
    )
    llm_retry_base_delay: float = Field(
        default=0.5, alias="LLM_RETRY_BASE_DELAY", gt=0.0, le=10.0
    )
    llm_retry_max_delay: float = Field(
        default=4.0, alias="LLM_RETRY_MAX_DELAY", gt=0.0, le=60.0
    )

    @property
    def repo_root(self) -> Path:
        return _REPO_ROOT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton accessor."""
    return Settings()
