"""
Configuration
=============
Reads all settings from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/pos_db"
    )
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
    MAX_ROWS_RETURNED: int = int(os.getenv("MAX_ROWS_RETURNED", "100"))
    LOG_FILE: str = os.getenv("LOG_FILE", "agent_logs.jsonl")

settings = Settings()

# Validate on startup
if not settings.ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is not set in .env")

if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")
