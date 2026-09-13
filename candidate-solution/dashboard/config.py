"""Configuration for the Streamlit dashboard (reads root .env when present)."""

import os

from dotenv import load_dotenv

load_dotenv()

database_url: str = os.getenv(
    "DATABASE_URL",
    "postgresql://agent_user:agent_password@localhost:5432/gen_ai_agent_db",
)
