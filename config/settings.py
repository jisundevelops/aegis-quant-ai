"""
config.settings — Pydantic Settings definition.

Reads all configuration from environment variables (and `.env` file when
present). Validates types and presence at startup, so missing or malformed
configuration fails fast instead of producing silent runtime errors.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application configuration.

    All fields map 1:1 to environment variables. Names are case-insensitive.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- Application ----------
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "Aegis Quant AI"
    app_version: str = "0.1.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    scheduler_enabled: bool = Field(default=True,
        description="Whether to start the APScheduler data fetcher on app startup.")

    # ---------- Database URLs (Phase 2 — take priority when set) ----------
    database_url: str = Field(default="", repr=False,
        description="Full SQLAlchemy async PostgreSQL DSN. Overrides individual POSTGRES_* fields when set.")
    redis_url: str = Field(default="", repr=False,
        description="Full Redis URL. Overrides individual REDIS_* fields when set.")

    # ---------- PostgreSQL (individual fields — fallback) ----------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "aegis"
    postgres_password: str = Field(default="", repr=False)
    postgres_db: str = "aegis_quant"
    postgres_pool_size: int = 10
    postgres_max_overflow: int = 20

    # ---------- Redis (individual fields — fallback) ----------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = Field(default="", repr=False)
    redis_db: int = 0
    redis_namespace: str = "aegis"

    # ---------- Binance ----------
    binance_api_key: str = Field(default="", repr=False)
    binance_api_secret: str = Field(default="", repr=False)
    binance_testnet: bool = False

    # ---------- Yahoo Finance ----------
    yfinance_user_agent: str = "AegisQuantAI/0.1"

    # ---------- MetaTrader 5 ----------
    mt5_login: int | None = None
    mt5_password: str = Field(default="", repr=False)
    mt5_server: str = ""
    mt5_path: str = ""

    # ---------- LLM providers ----------
    openai_api_key: str = Field(default="", repr=False)
    anthropic_api_key: str = Field(default="", repr=False)

    # ---------- News / sentiment ----------
    news_api_key: str = Field(default="", repr=False)
    alphavantage_api_key: str = Field(default="", repr=False)

    # ---------- Security ----------
    jwt_secret: str = Field(default="", repr=False)
    api_key_header: str = "X-Aegis-Key"

    # ---------- GitHub (for CI scripts only) ----------
    github_token: str = Field(default="", repr=False)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------
    @property
    def postgres_dsn(self) -> str:
        """Async SQLAlchemy-compatible PostgreSQL DSN.

        Priority:  DATABASE_URL  >  individual POSTGRES_* fields.
        """
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def effective_redis_url(self) -> str:
        """Redis connection URL.

        Priority:  REDIS_URL  >  individual REDIS_* fields.
        """
        if self.redis_url:
            return self.redis_url
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # ------------------------------------------------------------------
    # Validators
    # --------------------------------------------------------------------
    @field_validator("mt5_login", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        """Tolerate empty MT5_LOGIN in .env (treat as None)."""
        if v in ("", None):
            return None
        return v

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        return v.upper()

    @field_validator("jwt_secret")
    @classmethod
    def _warn_insecure_jwt(cls, v: str) -> str:
        if v and v.startswith("please-replace"):
            # Allow in non-production; fail loudly in production.
            return v
        return v

    @field_validator("database_url")
    @classmethod
    def _ensure_async_driver(cls, v: str) -> str:
        """If a sync postgres URL is provided, transparently upgrade to asyncpg."""
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def _validate_production_config(self) -> "Settings":
        """In production, DATABASE_URL and REDIS_URL MUST be set.

        Without this check, the code silently falls back to localhost
        when DATABASE_URL is missing — which causes [Errno 101] Network
        is unreachable on Render (no PostgreSQL on localhost).
        """
        import os
        # Only enforce in production AND when not loading from .env
        # (development can use individual POSTGRES_* fields)
        if self.app_env == "production":
            if not self.database_url:
                # Check if individual fields are set (non-default)
                using_individual = (
                    self.postgres_host != "localhost"
                    or self.postgres_password != ""
                )
                if not using_individual:
                    raise ValueError(
                        "DATABASE_URL is not set in production! "
                        "The code would fall back to localhost (which doesn't "
                        "exist on Render). Set DATABASE_URL in your Render "
                        "dashboard to your Supabase URL: "
                        "postgresql+asyncpg://postgres:PASSWORD@HOST:5432/DBNAME "
                        "(remember to URL-encode @ as %40 in the password)"
                    )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
