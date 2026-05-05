"""
Pending Approvals Store
========================
CRUD for the pending_approvals queue. Customer submissions land here;
ops console reads from here; ops decisions update here.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from config import settings

logger = logging.getLogger(__name__)


def _conn():
    return psycopg2.connect(settings.DATABASE_URL)


def enqueue(
    type:                str,
    payload:             Dict[str, Any],
    customer_session_id: str,
    customer_language:   str = "en",
) -> str:
    """Insert a PENDING row. Returns the new id."""
    new_id = str(uuid.uuid4())
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pending_approvals
                (id, type, payload, status, customer_session_id, customer_language)
            VALUES (%s, %s, %s::jsonb, 'PENDING', %s, %s)
            """,
            (new_id, type, json.dumps(payload), customer_session_id, customer_language),
        )
    logger.info(f"Enqueued {type} approval: {new_id[:8]} session={customer_session_id[:8]}")
    return new_id


def list_pending(limit: int = 50) -> List[Dict[str, Any]]:
    """List PENDING rows newest first (for ops queue UI)."""
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, type, payload, status, customer_session_id, customer_language,
                   agent_recommendation, created_at
            FROM pending_approvals
            WHERE status = 'PENDING'
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [_serialize(row) for row in cur.fetchall()]


def get(approval_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM pending_approvals WHERE id = %s",
            (approval_id,),
        )
        row = cur.fetchone()
        return _serialize(row) if row else None


def cache_recommendation(approval_id: str, recommendation: Dict[str, Any]) -> None:
    """Persist the approver agent's auto-generated recommendation."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pending_approvals SET agent_recommendation = %s::jsonb WHERE id = %s",
            (json.dumps(recommendation), approval_id),
        )


def mark_decided(
    approval_id:    str,
    decision:       str,        # "APPROVED" | "REJECTED"
    audit_summary:  str,
    decided_by:     str = "ops_console",
) -> None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pending_approvals
            SET status        = %s,
                decided_at    = %s,
                decided_by    = %s,
                audit_summary = %s
            WHERE id = %s
            """,
            (decision, datetime.utcnow(), decided_by, audit_summary, approval_id),
        )


def _serialize(row: dict) -> dict:
    """Convert datetimes to iso strings for JSON output."""
    out = dict(row)
    for k, v in out.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out
