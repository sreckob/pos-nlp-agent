"""
state_validator.py — DB state validation for write operations
=============================================================
Tests that dispute reversal and loyalty credit write operations actually
change the database correctly. Compares before/after state rather than
just trusting the agent's words.

Usage:
    cd validation
    python state_validator.py                          # local backend
    python state_validator.py --url http://localhost:8000
    python state_validator.py --url https://pos-nlp-agent-production.up.railway.app

Requires:
    - Backend running
    - DATABASE_URL and OPS_API_KEY in backend/files/.env
    - demo_seed.py already run (provides seeded dispute pairs + loyalty gaps)
"""

import argparse
import os
import sys
import json
import time
import uuid
from datetime import datetime

import requests
import psycopg2
from dotenv import load_dotenv

# Load .env from backend/files
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "files", ".env")
load_dotenv(ENV_PATH)

DATABASE_URL = os.getenv("DATABASE_URL")
OPS_API_KEY  = os.getenv("OPS_API_KEY", "")
DEFAULT_URL  = "http://localhost:8000"

DEMO_PAN_VISA = "411111******4242"


# ── DB helpers ────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(DATABASE_URL)


def get_tx_status(tx_id: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT transaction_id, status, dispute_status, resolved_at "
                "FROM transactions WHERE transaction_id = %s",
                (tx_id,)
            )
            row = cur.fetchone()
    if not row:
        return {}
    return {"transaction_id": str(row[0]), "status": row[1],
            "dispute_status": row[2], "resolved_at": str(row[3])}


def get_loyalty_points(pan: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT points FROM loyalty_accounts WHERE pan_masked = %s", (pan,)
            )
            row = cur.fetchone()
    return row[0] if row else None


def get_seeded_dispute_pair() -> tuple:
    """Return (original_tx_id, duplicate_tx_id) for the Maxi/4242 demo dispute pair."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t1.transaction_id, t2.transaction_id
                FROM transactions t1
                JOIN transactions t2
                  ON t1.pan_masked = t2.pan_masked
                 AND t1.merchant_id = t2.merchant_id
                 AND t1.amount = t2.amount
                 AND t1.transaction_id != t2.transaction_id
                 AND t1.status = 'APPROVED'
                 AND t2.status = 'APPROVED'
                 AND t1.approval_code != t2.approval_code
                WHERE t1.pan_masked = %s
                  AND ABS(EXTRACT(EPOCH FROM (t1.transaction_date - t2.transaction_date))) < 1800
                LIMIT 1
            """, (DEMO_PAN_VISA,))
            row = cur.fetchone()
    if not row:
        return None, None
    return str(row[0]), str(row[1])


def get_uncredited_points(pan: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(loyalty_points_earned), 0)
                FROM transactions
                WHERE pan_masked = %s
                  AND loyalty_points_earned > 0
                  AND loyalty_points_credited = FALSE
                  AND status = 'APPROVED'
            """, (pan,))
            row = cur.fetchone()
    return int(row[0]) if row else 0


# ── REST helpers ──────────────────────────────────────────────

def submit_dispute(base_url: str, session_id: str, original_id: str, duplicate_id: str) -> dict:
    r = requests.post(f"{base_url}/dispute/submit", json={
        "customer_session_id": session_id,
        "original_tx_id":      original_id,
        "duplicate_tx_id":     duplicate_id,
        "pan_masked":          DEMO_PAN_VISA,
    }, timeout=15)
    r.raise_for_status()
    return r.json()


def submit_loyalty(base_url: str, session_id: str, pan: str, points: int) -> dict:
    r = requests.post(f"{base_url}/loyalty/submit", json={
        "customer_session_id": session_id,
        "pan_masked":          pan,
        "points_to_add":       points,
    }, timeout=15)
    r.raise_for_status()
    return r.json()


def ops_decide(base_url: str, approval_id: str, action: str) -> dict:
    r = requests.post(
        f"{base_url}/ops/decide",
        json={"approval_id": approval_id, "decision": action.upper()},
        headers={"X-Ops-Key": OPS_API_KEY},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── Test cases ────────────────────────────────────────────────

def run_dispute_reversal_test(base_url: str) -> dict:
    result = {"name": "dispute_reversal_state", "passed": False, "details": []}

    original_id, duplicate_id = get_seeded_dispute_pair()
    if not original_id:
        result["details"].append("SKIP: no seeded dispute pair found — run demo_seed.py first")
        result["passed"] = None  # skip
        return result

    # Before state
    before_dup = get_tx_status(duplicate_id)
    result["details"].append(f"Before: duplicate status={before_dup.get('status')} dispute_status={before_dup.get('dispute_status')}")

    # Submit dispute
    session_id = f"state-val-{uuid.uuid4().hex[:8]}"
    sub = submit_dispute(base_url, session_id, original_id, duplicate_id)
    approval_id = sub.get("submission_id")
    if not approval_id:
        result["details"].append(f"FAIL: submit returned no submission_id: {sub}")
        return result
    result["details"].append(f"Submitted: submission_id={approval_id}")

    # Ops approve
    time.sleep(1)
    decision = ops_decide(base_url, approval_id, "approve")
    result["details"].append(f"Ops decision: {decision.get('status')} agent_decision={decision.get('agent_decision')}")

    # After state
    time.sleep(1)
    after_dup = get_tx_status(duplicate_id)
    result["details"].append(f"After:  duplicate status={after_dup.get('status')} dispute_status={after_dup.get('dispute_status')}")

    # Assert
    checks = [
        (after_dup.get("status") == "REVERSED",       "duplicate.status = REVERSED"),
        (after_dup.get("dispute_status") == "APPROVED","duplicate.dispute_status = APPROVED"),
        (after_dup.get("resolved_at") != "None",       "duplicate.resolved_at is set"),
    ]
    passed = True
    for ok, label in checks:
        symbol = "✓" if ok else "✗"
        result["details"].append(f"  {symbol} {label}")
        if not ok:
            passed = False

    result["passed"] = passed
    return result


def run_loyalty_credit_test(base_url: str) -> dict:
    result = {"name": "loyalty_credit_state", "passed": False, "details": []}

    pan = DEMO_PAN_VISA
    uncredited = get_uncredited_points(pan)
    if uncredited == 0:
        result["details"].append("SKIP: no uncredited loyalty points — run demo_seed.py first")
        result["passed"] = None
        return result

    points_before = get_loyalty_points(pan)
    result["details"].append(f"Before: loyalty_accounts.points={points_before}, uncredited_points={uncredited}")

    session_id = f"state-val-{uuid.uuid4().hex[:8]}"
    sub = submit_loyalty(base_url, session_id, pan, uncredited)
    approval_id = sub.get("submission_id")
    if not approval_id:
        result["details"].append(f"FAIL: submit returned no submission_id: {sub}")
        return result
    result["details"].append(f"Submitted: submission_id={approval_id}, points_to_add={uncredited}")

    time.sleep(1)
    decision = ops_decide(base_url, approval_id, "approve")
    result["details"].append(f"Ops decision: {decision.get('status')} agent_decision={decision.get('agent_decision')}")

    time.sleep(1)
    points_after = get_loyalty_points(pan)
    remaining_uncredited = get_uncredited_points(pan)
    result["details"].append(f"After:  loyalty_accounts.points={points_after}, uncredited_remaining={remaining_uncredited}")

    expected_points = points_before + uncredited
    checks = [
        (points_after == expected_points,   f"points increased by {uncredited} ({points_before} → {expected_points})"),
        (remaining_uncredited == 0,         "all uncredited transactions now credited"),
    ]
    passed = True
    for ok, label in checks:
        symbol = "✓" if ok else "✗"
        result["details"].append(f"  {symbol} {label}")
        if not ok:
            passed = False

    result["passed"] = passed
    return result


def run_ops_auth_test(base_url: str) -> dict:
    """Verify ops endpoints reject requests without OPS_API_KEY."""
    result = {"name": "ops_auth_required", "passed": False, "details": []}
    try:
        r = requests.get(f"{base_url}/ops/queue", timeout=10)
        if r.status_code in (401, 403, 422):
            result["details"].append(f"✓ /ops/queue blocked without key (HTTP {r.status_code})")
            result["passed"] = True
        else:
            result["details"].append(f"✗ /ops/queue returned {r.status_code} without key — auth not enforced")
    except Exception as e:
        result["details"].append(f"ERROR: {e}")
    return result


# ── Main ──────────────────────────────────────────────────────

def run_all(base_url: str) -> dict:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set — check backend/files/.env")
        sys.exit(1)
    if not OPS_API_KEY:
        print("WARNING: OPS_API_KEY not set — ops_decide calls will fail")

    print(f"State Validator — {base_url}")
    print("=" * 55)

    tests = [
        run_ops_auth_test,
        run_dispute_reversal_test,
        run_loyalty_credit_test,
    ]

    results = []
    passed = skipped = failed = 0

    for test_fn in tests:
        print(f"\nRunning: {test_fn.__name__.replace('run_', '')}...")
        r = test_fn(base_url)
        results.append(r)
        for line in r["details"]:
            print(f"  {line}")
        if r["passed"] is True:
            passed += 1
            print(f"  → PASSED")
        elif r["passed"] is None:
            skipped += 1
            print(f"  → SKIPPED")
        else:
            failed += 1
            print(f"  → FAILED")

    print(f"\n{'='*55}")
    print(f"State validation: {passed} passed, {failed} failed, {skipped} skipped")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "base_url": base_url,
        "summary": {"passed": passed, "failed": failed, "skipped": skipped},
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",    default=DEFAULT_URL)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_all(args.url)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"Report saved to: {args.output}")
