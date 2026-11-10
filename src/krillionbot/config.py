from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    db_path: str = "./data/krillion.db"
    # Nudge people who haven't posted today's dive, at this Singapore hour (24h). 0 disables.
    nudge_hour_sgt: int = 21
    # Minutes before the next dive opens to post the day's wrap-up.
    wrap_minutes_before_reset: int = 10
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
