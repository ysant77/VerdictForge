from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings (env-driven)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Storage
    database_url: str = "sqlite+aiosqlite:///./data/legaldata.db"
    raw_store_dir: Path = Path("data/raw")

    # Crawl politeness
    max_concurrency: int = 5
    min_delay_s: float = 0.35
    max_retries: int = 5
    timeout_s: float = 30.0

    # Source defaults
    source_base_url: str = "https://www.elitigation.sg"
    # Paginated listing endpoint for Supreme Court judgments
    source_listing_url: str = "https://www.elitigation.sg/gdviewer/SUPCT"


settings = Settings()
