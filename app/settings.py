from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_owner_id: int = 0
    database_url: str = "sqlite:///data/smart_building.db"
    storage_dir: Path = Path("storage")
    currency: str = "YER"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
