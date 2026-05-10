"""
Centralized application settings loaded from environment variables.
Uses pydantic-settings for validation and type safety.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration loaded from .env file."""

    # --- Telegram ---
    telegram_bot_token: str = ""

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None

    # --- SerpApi ---
    serpapi_api_key: str = ""

    # --- Database ---
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'jobfinder.db'}"

    # --- Security ---
    allowed_user_ids: list[int] = []

    # --- Job Search Defaults ---
    default_regions: list[str] = ["Saudi Arabia", "United Arab Emirates"]
    default_roles: list[str] = [
        "SAP ABAP Consultant",
        "SAP MM Consultant",
        "SAP EWM Consultant",
        "Solution Architect",
    ]

    # --- Scheduler ---
    scrape_interval_minutes: int = 60
    min_match_score: int = 7

    # --- Logging ---
    log_level: str = "INFO"

    # --- Paths ---
    data_dir: Path = BASE_DIR / "data"
    output_dir: Path = BASE_DIR / "output"
    templates_dir: Path = BASE_DIR / "templates"

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_user_ids(cls, v: str | list) -> list[int]:
        """Parse comma-separated user IDs from env string."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
        return v

    @field_validator("default_regions", "default_roles", mode="before")
    @classmethod
    def parse_csv_list(cls, v: str | list) -> list[str]:
        """Parse comma-separated lists from env string."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()
