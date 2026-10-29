"""Configuration loaded from .env."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Urja Meter API"
    data_source: Literal["sample", "live"] = "sample"
    portal_base_url: str = "https://urja-ops.flockenergy.tech"
    # Optional for automatic authentication; never commit actual values.
    portal_email: str = ""
    portal_password: str = ""
    # Optional pre-existing session. With credentials, an expired session is renewed once.
    portal_session_cookie: str = ""
    # Local export snapshot, refreshed on demand via scripts.refresh_export.
    meter_export_path: str = "data/meter-export.json"
    portal_timezone: str = "Asia/Kolkata"  # Assumption, NOT confirmed by portal responses.
    upstream_timeout_seconds: float = 15.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
