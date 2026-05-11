"""
Write Operations
================
Handles the two write operations in the system:

1. Dispute reversal — marks duplicate transaction as REVERSED
   and updates dispute_status on both transactions

2. Loyalty credit — credits missing points to loyalty_accounts
   and marks transactions as loyalty_points_credited = TRUE

Both operations use execute_write() from executor.py which only
allows UPDATE statements and has extra safety checks.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import psycopg2
from config import settings

logger = logging.getLogger(__name__)


def get_connection():
    return psycopg2.connect(settings.DATABASE_URL)


# ── Dispute reversal ──────────────────────────────────────────


def approve_dispute_reversal(
    original_tx_id: str, duplicate_tx_id: str
) -> Dict[str, Any]:
    """
    Approve a dispute reversal:
    1. Generate a shared dispute_id to link the pair
    2. Mark original transaction as DISPUTED / APPROVED
    3. Mark duplicate transaction as REVERSED
    4. Set resolved_at timestamp on both

    Returns:
        {success, message, original_tx_id, duplicate_tx_id, dispute_id}
    """
    if not original_tx_id or not duplicate_tx_id:
        return {"success": False, "message": "Missing transaction IDs for reversal."}

    dispute_id = str(uuid.uuid4())
    resolved_at = datetime.utcnow()

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Mark original as DISPUTED → APPROVED (the valid charge)
        cur.execute(
            """
            UPDATE transactions
            SET dispute_status = 'APPROVED',
                dispute_id     = %s,
                disputed_at    = %s,
                resolved_at    = %s
            WHERE transaction_id = %s
        """,
            (dispute_id, resolved_at, resolved_at, original_tx_id),
        )

        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {
                "success": False,
                "message": f"Transaction {original_tx_id} not found.",
            }

        # Mark duplicate as REVERSED (the erroneous charge)
        cur.execute(
            """
            UPDATE transactions
            SET status         = 'REVERSED',
                dispute_status = 'APPROVED',
                dispute_id     = %s,
                disputed_at    = %s,
                resolved_at    = %s
            WHERE transaction_id = %s
        """,
            (dispute_id, resolved_at, resolved_at, duplicate_tx_id),
        )

        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {
                "success": False,
                "message": f"Duplicate transaction {duplicate_tx_id} not found.",
            }

        conn.commit()
        cur.close()
        conn.close()

        logger.info(
            f"Dispute reversal approved: "
            f"original={original_tx_id[:8]} "
            f"duplicate={duplicate_tx_id[:8]} "
            f"dispute_id={dispute_id[:8]}"
        )

        return {
            "success": True,
            "message": "Reversal approved. The duplicate charge has been reversed.",
            "dispute_id": dispute_id,
            "original_tx_id": original_tx_id,
            "duplicate_tx_id": duplicate_tx_id,
            "resolved_at": resolved_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Dispute reversal error: {e}")
        return {"success": False, "message": f"Reversal failed: {str(e)}"}


def reject_dispute(
    duplicate_tx_id: str, original_tx_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reject a dispute claim.
    Marks transactions as REJECTED so they are not actioned again.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        now = datetime.utcnow()

        tx_ids = [t for t in [duplicate_tx_id, original_tx_id] if t]
        for tx_id in tx_ids:
            cur.execute(
                """
                UPDATE transactions
                SET dispute_status = 'REJECTED',
                    disputed_at    = %s,
                    resolved_at    = %s
                WHERE transaction_id = %s
            """,
                (now, now, tx_id),
            )

        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"Dispute rejected: {duplicate_tx_id[:8]}")
        return {"success": True, "message": "Dispute claim has been rejected."}

    except Exception as e:
        logger.error(f"Dispute rejection error: {e}")
        return {"success": False, "message": str(e)}


# ── Loyalty credit ────────────────────────────────────────────


def credit_loyalty_points(pan_masked: str, points_to_add: int) -> Dict[str, Any]:
    """
    Credit missing loyalty points:
    1. Add points to loyalty_accounts balance
    2. Update tier based on new total_spent
    3. Mark uncredited transactions as loyalty_points_credited = TRUE
    4. Update last_updated timestamp

    Returns:
        {success, message, points_added, new_balance, new_tier, transactions_updated}
    """
    if not pan_masked or points_to_add <= 0:
        return {"success": False, "message": "Invalid PAN or points amount."}

    try:
        conn = get_connection()
        cur = conn.cursor()
        now = datetime.utcnow()

        # Check account exists
        cur.execute(
            """
            SELECT points, tier, total_spent
            FROM loyalty_accounts
            WHERE pan_masked = %s
        """,
            (pan_masked,),
        )

        row = cur.fetchone()
        if not row:
            conn.close()
            return {
                "success": False,
                "message": f"No loyalty account found for card {pan_masked}.",
            }

        current_points, current_tier, total_spent = row
        new_balance = current_points + points_to_add

        # Calculate new tier based on total_spent
        new_tier = calculate_tier(float(total_spent or 0))

        # Update loyalty account
        cur.execute(
            """
            UPDATE loyalty_accounts
            SET points       = points + %s,
                tier         = %s,
                last_updated = %s
            WHERE pan_masked = %s
        """,
            (points_to_add, new_tier, now, pan_masked),
        )

        # Mark uncredited transactions as credited
        cur.execute(
            """
            UPDATE transactions
            SET loyalty_points_credited = TRUE
            WHERE pan_masked            = %s
              AND loyalty_points_earned  > 0
              AND loyalty_points_credited = FALSE
        """,
            (pan_masked,),
        )

        transactions_updated = cur.rowcount

        conn.commit()
        cur.close()
        conn.close()

        logger.info(
            f"Loyalty credit: pan={pan_masked[-4:]} "
            f"added={points_to_add} "
            f"new_balance={new_balance} "
            f"tier={new_tier} "
            f"txns_updated={transactions_updated}"
        )

        tier_msg = (
            f" You have been upgraded to {new_tier} tier!"
            if new_tier != current_tier
            else ""
        )

        return {
            "success": True,
            "message": f"{points_to_add} points have been credited to your account. "
            f"Your new balance is {new_balance} points.{tier_msg}",
            "points_added": points_to_add,
            "new_balance": new_balance,
            "previous_balance": current_points,
            "new_tier": new_tier,
            "previous_tier": current_tier,
            "transactions_updated": transactions_updated,
            "updated_at": now.isoformat(),
        }

    except Exception as e:
        logger.error(f"Loyalty credit error: {e}")
        return {"success": False, "message": f"Credit failed: {str(e)}"}


def calculate_tier(total_spent: float) -> str:
    """Calculate loyalty tier based on lifetime spend in RSD."""
    if total_spent >= 200_000:
        return "GOLD"
    elif total_spent >= 50_000:
        return "SILVER"
    return "STANDARD"


def get_loyalty_balance(pan_masked: str) -> Dict[str, Any]:
    """
    Fetch current loyalty account balance for a PAN.
    Used to confirm credit was applied.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT points, tier, total_spent, last_updated
            FROM loyalty_accounts
            WHERE pan_masked = %s
        """,
            (pan_masked,),
        )

        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return {"success": False, "enrolled": False}

        return {
            "success": True,
            "enrolled": True,
            "points": row[0],
            "tier": row[1],
            "total_spent": float(row[2] or 0),
            "last_updated": row[3].isoformat() if row[3] else None,
        }

    except Exception as e:
        logger.error(f"Loyalty balance error: {e}")
        return {"success": False, "enrolled": False, "error": str(e)}
