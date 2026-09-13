"""Configuration for the MCP server."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    location_service_url: str = "http://localhost:8001"
    mcp_server_port: int = 8003


settings = Settings()