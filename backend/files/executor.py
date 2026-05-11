"""
SQL Executor + Excel Exporter
==============================
Executes SELECT queries against PostgreSQL.
Read-only guard blocks any destructive statements.
Excel export using openpyxl for merchant path.
"""

import io
import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from config import settings
from db import get_conn

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
    upper = sql.upper()
    for pattern in BLOCKED_KEYWORDS:
        if re.search(pattern, upper):
            logger.warning(f"Blocked unsafe SQL: {sql[:80]}")
            return False
    return True


def serialize_row(row: dict) -> dict:
    """Convert non-JSON-serializable types."""
    clean = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            clean[k] = v.isoformat()
        elif isinstance(v, Decimal):
            clean[k] = float(v)
        else:
            clean[k] = v
    return clean


def execute_query(sql: str, params: tuple = None) -> Dict[str, Any]:
    """
    Execute a safe SELECT query and return results.
    Pass untrusted values via params — psycopg2 escapes them safely.
    Returns: {success, rows, row_count, error}
    """
    if not is_safe_sql(sql):
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "error": "Query blocked: only SELECT statements are allowed.",
        }

    sql = sql.strip().rstrip(";")

    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {settings.MAX_ROWS_RETURNED}"

    try:
        with get_conn() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params)
            rows = [serialize_row(dict(row)) for row in cur.fetchall()]
            cur.close()
        return {"success": True, "rows": rows, "row_count": len(rows), "error": None}

    except psycopg2.Error as e:
        logger.error(f"DB error: {e}")
        return {"success": False, "rows": [], "row_count": 0, "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"success": False, "rows": [], "row_count": 0, "error": str(e)}


def execute_write(sql: str, params: tuple = None) -> Dict[str, Any]:
    """
    Execute a write query (UPDATE only — for loyalty credit and dispute resolution).
    Only called by the loyalty and dispute agents after validation.
    """
    # Extra safety — only allow UPDATE
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("UPDATE"):
        return {
            "success": False,
            "error": "Only UPDATE statements allowed via execute_write",
        }

    # Block dangerous patterns even in UPDATE
    for pattern in [r"\bDROP\b", r"\bDELETE\b", r"\bTRUNCATE\b", r"\bALTER\b"]:
        if re.search(pattern, sql_upper):
            return {"success": False, "error": "Blocked unsafe keyword in UPDATE"}

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        cur = conn.cursor()
        cur.execute(sql, params)
        affected = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "rows_affected": affected, "error": None}

    except psycopg2.Error as e:
        logger.error(f"Write error: {e}")
        return {"success": False, "rows_affected": 0, "error": str(e)}


def export_to_excel(rows: List[Dict]) -> bytes:
    """
    Convert a list of row dicts to an Excel file in memory.
    Returns bytes that can be sent as a file download.
    Requires: pip install openpyxl
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Transactions"

        if not rows:
            ws["A1"] = "No data"
            buf = io.BytesIO()
            wb.save(buf)
            return buf.getvalue()

        # Header row
        headers = list(rows[0].keys())
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(
                row=1, column=col_idx, value=header.upper().replace("_", " ")
            )
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F5C9E")
            cell.alignment = Alignment(horizontal="center")

        # Data rows
        for row_idx, row in enumerate(rows, 2):
            for col_idx, header in enumerate(headers, 1):
                val = row.get(header)
                # Format timestamps nicely
                if isinstance(val, str) and "T" in val and ":" in val:
                    val = val.replace("T", " ")[:19]
                ws.cell(row=row_idx, column=col_idx, value=val)

        # Auto-size columns
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    except ImportError:
        logger.error("openpyxl not installed — run: pip install openpyxl")
        raise
