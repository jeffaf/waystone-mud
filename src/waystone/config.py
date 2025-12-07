"""Configuration management for Waystone MUD using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="WAYSTONE_",
        extra="ignore",
    )

    # Server Settings
    host: str = Field(default="0.0.0.0", description="Server bind address")
    telnet_port: int = Field(default=4000, description="Telnet server port")
    websocket_port: int = Field(default=4001, description="WebSocket server port")
    debug: bool = Field(default=False, description="Enable debug mode")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/waystone.db",
        description="Database connection URL",
        alias="DATABASE_URL",
    )

    # Session Settings
    session_secret: str = Field(
        default="change-me-in-production",
        description="Secret key for session signing",
        alias="SESSION_SECRET",
    )
    session_timeout_minutes: int = Field(
        default=60, description="Session timeout in minutes", alias="SESSION_TIMEOUT_MINUTES"
    )

    # Game Settings
    starting_room_id: str = Field(
        default="university_main_gates",
        description="Room ID where new characters spawn",
        alias="STARTING_ROOM_ID",
    )
    max_connections_per_ip: int = Field(
        default=5, description="Max simultaneous connections per IP", alias="MAX_CONNECTIONS_PER_IP"
    )
    command_rate_limit: int = Field(
        default=10,
        description="Max commands per second per connection",
        alias="COMMAND_RATE_LIMIT_PER_SECOND",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level", alias="LOG_LEVEL")
    log_format: str = Field(
        default="console", description="Log format (console or json)", alias="LOG_FORMAT"
    )

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return Path("./data")

    @property
    def world_dir(self) -> Path:
        """Get the world data directory path."""
        return self.data_dir / "world"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
