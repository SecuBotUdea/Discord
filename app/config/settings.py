from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    database_url: str = Field(default="memory://local", alias="DATABASE_URL")
    http_port: int = Field(default=8000, alias="HTTP_PORT")
    discord_log_level: str = Field(default="INFO", alias="DISCORD_LOG_LEVEL")
    routing_service_url: str | None = Field(default=None, alias="ROUTING_SERVICE_URL")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    allowed_origins: str = Field(default="", alias="ALLOWED_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
