import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    discord_token: str
    database_url: str
    dev_guild_id: int | None
    log_level: str = "INFO"
    log_json: bool = False


def load_settings() -> Settings:
    load_dotenv()
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    guild = os.environ.get("DEV_GUILD_ID", "").strip()
    return Settings(
        discord_token=token,
        database_url=db_url,
        dev_guild_id=int(guild) if guild else None,
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        log_json=os.environ.get("LOG_FORMAT", "").lower() == "json",
    )
