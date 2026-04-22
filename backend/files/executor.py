"""
SQL Executor
============
Executes SELECT queries against PostgreSQL.
Read-only guard blocks any destructive statements.
"""

import logging
import re
from decimal import Decimal
from typing import Any, Dict

import psycopg2
import psycopg2.extras

from config import settings

logger = logging.getLogger(__name__)

# ── Blocked SQL keywords ──────────────────────────────────────
BLOCKED_KEYWORDS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXECUTE\b",
    r"\bCALL\b",
]

def is_safe_sql(sql: str) -> bool:
    """Return True only if the SQL contains no destructive keywords."""
    upper = sql.upper()
    for pattern in BLOCKED_KEYWORDS:
        if re.search(pattern, upper):
            logger.warning(f"Blocked unsafe SQL keyword in: {sql[:100]}")
            return False
    return True


def serialize_row(row: dict) -> dict:
    """Convert non-JSON-serializable types to strings."""
    clean = {}
    for k, v in row.items():
        if hasattr(v, 'isoformat'):
            # datetime, date, time objects
            clean[k] = v.isoformat()
        elif isinstance(v, Decimal):
            # Decimal → float
            clean[k] = float(v)
        else:
            clean[k] = v
    return clean


def execute_query(sql: str) -> Dict[str, Any]:
    """
    Execute a SQL SELECT query and return results.

    Returns:
        {
            "success": bool,
            "rows": list[dict],
            "row_count": int,
            "error": str | None
        }
    """
    # Safety check
    if not is_safe_sql(sql):
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "error": "Query blocked: only SELECT statements are allowed."
        }

    # Strip trailing semicolons
    sql = sql.strip().rstrip(";")

    # Add row limit if not already present
    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {settings.MAX_ROWS_RETURNED}"

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(sql)
        rows = [serialize_row(dict(row)) for row in cur.fetchall()]

        cur.close()
        conn.close()

        return {
            "success": True,
            "rows": rows,
            "row_count": len(rows),
            "error": None
        }

    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Unexpected error executing query: {e}")
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "error": str(e)
        }
