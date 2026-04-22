"""
Structured Logger
=================
Appends one JSON line per query turn to agent_logs.jsonl
Each line contains: timestamp, session_id, user prompt,
generated SQL, row count, latency, and any error.

To read logs:
    cat agent_logs.jsonl | python -m json.tool   # pretty print last entry
    grep "DECLINED" agent_logs.jsonl             # search by keyword
"""

import json
import logging
from datetime import datetime
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def log_query(
    session_id:   str,
    user_message: str,
    sql:          Optional[str],
    row_count:    int,
    latency_ms:   int,
    error:        Optional[str] = None
):
    """Append a structured log entry to the log file."""
    entry = {
        "timestamp":    datetime.utcnow().isoformat(),
        "session_id":   session_id,
        "user_message": user_message,
        "sql":          sql,
        "row_count":    row_count,
        "latency_ms":   latency_ms,
        "error":        error,
        "success":      error is None
    }

    try:
        with open(settings.LOG_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write log entry: {e}")
