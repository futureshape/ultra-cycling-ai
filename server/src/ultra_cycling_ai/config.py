"""Application configuration loaded from environment / .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is read from environment variables (or a .env file)."""

    openai_api_key: str = "sk-not-set"
    openai_model: str = "gpt-4o"
    database_url: str = "sqlite+aiosqlite:///./data/ride.db"
    tick_interval_seconds: int = 120
    default_cooldown_minutes: int = 15

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
