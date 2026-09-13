"""Configuration for the analyzer agent."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    agent_port: int = 8000
    mcp_server_url: str = "http://localhost:8003/sse"
    location_service_url: str = "http://localhost:8001"
    database_url: str = (
        "postgresql://agent_user:agent_password@localhost:5432/gen_ai_agent_db"
    )

    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    bedrock_model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0"


settings = Settings()