"""Centralised configuration using Pydantic Settings.
All secrets loaded from environment variables / AWS SSM.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── App ─────────────────────────────────────────────────────────────────
    APP_ENV: str = "development"  # development | staging | production
    LOG_LEVEL: str = "INFO"
    BASE_URL: str = "https://your-api-gateway-url.execute-api.ap-south-1.amazonaws.com/prod"
    API_SECRET_KEY: str = "change-me-in-production"

    # ─── WhatsApp Business API ────────────────────────────────────────────
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""

    # ─── AWS ─────────────────────────────────────────────────────────────────
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    DYNAMODB_TABLE_NAME: str = "trip-orchestrator-trips"
    S3_BUCKET_NAME: str = "trip-orchestrator-receipts"
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    BEDROCK_REGION: str = "us-east-1"

    # ─── Spotify ─────────────────────────────────────────────────────────────
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    SPOTIFY_REDIRECT_URI: str = ""

    # ─── Google Maps ──────────────────────────────────────────────────────────
    GOOGLE_MAPS_API_KEY: str = ""

    # ─── Razorpay ─────────────────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # ─── Gemini ──────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""

    # ─── Redis Cache ──────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL_SECONDS: int = 300

    # ─── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = None
    DATADOG_API_KEY: Optional[str] = None
    DATADOG_APP_KEY: Optional[str] = None
    ENABLE_TRACING: bool = True

    # ─── Feature Flags ────────────────────────────────────────────────────────
    ENABLE_SPOTIFY: bool = True
    ENABLE_RAZORPAY: bool = True
    ENABLE_OCR: bool = True
    ENABLE_MAPS: bool = True
    ENABLE_SOS: bool = True
    MAX_TRIP_MEMBERS: int = 50
    MAX_CONCURRENT_TRIPS: int = 10000

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


# Module-level singleton
settings = get_settings()
