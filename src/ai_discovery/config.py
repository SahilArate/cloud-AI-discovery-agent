"""Application settings, loaded once from environment variables and .env."""

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ScanMode(str, Enum):
    MOCK = "mock"
    LIVE = "live"


class Settings(BaseSettings):
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        
    )

    database_url: str = "postgresql+psycopg://discovery:discovery@localhost:5432/ai_discovery"
    scan_mode: ScanMode = ScanMode.MOCK
    groq_api_key: str = ""
    small_model_name: str = "openai/gpt-oss-20b"
    large_model_name: str = "openai/gpt-oss-120b"


@lru_cache
def get_settings() -> Settings:
    return Settings()