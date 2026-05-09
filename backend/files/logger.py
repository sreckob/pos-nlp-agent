"""
Structured Logger
=================
Appends one JSON line per query turn to agent_logs.jsonl
"""

import json
import logging
from datetime import datetime
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def log_query(
    session_id: str,
    user_message: str,
    role: str,
    sql: Optional[str],
    row_count: int,
    latency_ms: int,
    error: Optional[str] = None,
):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "role": role,
        "user_message": user_message,
        "sql": sql,
        "row_count": row_count,
        "latency_ms": latency_ms,
        "error": error,
        "success": error is None,
    }
    try:
        with open(settings.LOG_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write log: {e}")
