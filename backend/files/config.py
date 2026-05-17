"""
Configuration
=============
Reads all settings from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # ── Multi-LLM config ─────────────────────────────────────
    # LLM_MODEL: any litellm model string.
    #   Anthropic: "claude-sonnet-4-6"
    #   Gemini:    "gemini/gemini-1.5-flash"
    #   Mistral:   "mistral/mistral-small-latest"
    # Defaults to CLAUDE_MODEL so existing setups need no change.
    LLM_MODEL: str  = os.getenv("LLM_MODEL",    os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"))
    # VISION_MODEL: used for receipt OCR in the dispute path.
    # Kept on Claude by default — most reliable for document understanding.
    VISION_MODEL: str = os.getenv("VISION_MODEL", os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"))

    # Provider API keys (only set the ones you use)
    GOOGLE_API_KEY:  str = os.getenv("GOOGLE_API_KEY",  "")
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    MAX_ROWS_RETURNED: int = int(os.getenv("MAX_ROWS_RETURNED", "100"))
    LOG_FILE: str = os.getenv("LOG_FILE", "agent_logs.jsonl")
    OPS_API_KEY: str = os.getenv("OPS_API_KEY", "")

    # RAG: set to "false" to disable regulation clause retrieval in the approver agent
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "true").lower() not in ("false", "0", "no")

    # Temperature per node — override via env vars or tune_temperature.py sweep
    TEMPERATURES: dict = {
        "router":     float(os.getenv("TEMP_ROUTER",     "0.0")),
        "cardholder": float(os.getenv("TEMP_CARDHOLDER", "0.0")),
        "merchant":   float(os.getenv("TEMP_MERCHANT",   "0.0")),
        "dispute":    float(os.getenv("TEMP_DISPUTE",    "0.0")),
        "loyalty":    float(os.getenv("TEMP_LOYALTY",    "0.0")),
        "approver":   float(os.getenv("TEMP_APPROVER",   "0.0")),
    }


settings = Settings()

# Validate on startup
if not settings.ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY is not set in .env")

if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")
