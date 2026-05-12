"""
Approval Agent
==============
Operations-side LLM that reviews customer-submitted disputes and loyalty
credit requests. Produces an audit-grade decision that gates the actual
write_ops call. Distinct from the chat agent (agent.py) — never speaks
to the customer.

Public functions:
    review_dispute(original_tx_id, duplicate_tx_id) -> decision dict
    review_loyalty_credit(pan_masked, points_to_add) -> decision dict

Decision shape:
    {
      "decision":         "APPROVE" | "REJECT",
      "confidence":       0.0-1.0,
      "audit_summary":    "one-line operations log entry",
      "blocking_reason":  "why rejected, or null"
    }
"""

import json
import logging
import re
from typing import Any, Dict, List

from config import settings
from executor import execute_query
from llm_client import complete
from prompts import DISPUTE_APPROVAL_PROMPT, LOYALTY_APPROVAL_PROMPT

logger = logging.getLogger(__name__)


def _parse_json(raw: str) -> Dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("approval agent returned no JSON")
    return json.loads(match.group(0))


def _call_claude(system: str, payload: str) -> Dict:
    raw = complete(
        system      = system,
        messages    = [{"role": "user", "content": payload}],
        max_tokens  = 400,
        temperature = settings.TEMPERATURES.get("approver", 0.0),
    )
    return _parse_json(raw)


def _reject(reason: str) -> Dict[str, Any]:
    return {
        "decision": "REJECT",
        "confidence": 1.0,
        "audit_summary": f"Auto-reject: {reason}",
        "blocking_reason": reason,
    }


# ── Dispute review ────────────────────────────────────────────


def _fetch_tx(tx_id: str) -> Dict:
    if not tx_id:
        return {}
    r = execute_query(
        "SELECT transaction_id, transaction_date, amount, currency, status, "
        "approval_code, pan_masked, merchant_id, merchant_name "
        "FROM transactions WHERE transaction_id = %s",
        (str(tx_id),),
    )
    return r["rows"][0] if r.get("rows") else {}


def review_dispute(original_tx_id: str, duplicate_tx_id: str) -> Dict[str, Any]:
    """Review a dispute reversal request. Returns decision dict."""
    original = _fetch_tx(original_tx_id)
    duplicate = _fetch_tx(duplicate_tx_id)

    if not original or not duplicate:
        return _reject("one or both transactions not found in DB")

    # Hard pre-checks before LLM (cheap guard)
    if original.get("pan_masked") != duplicate.get("pan_masked"):
        return _reject("PAN mismatch between original and duplicate")
    if float(original.get("amount", 0)) != float(duplicate.get("amount", 0)):
        return _reject("amount mismatch")
    if original.get("merchant_id") != duplicate.get("merchant_id"):
        return _reject("merchant mismatch")
    if original.get("status") == "REVERSED" or duplicate.get("status") == "REVERSED":
        return _reject("transaction already reversed")

    payload = (
        f"Action: DISPUTE_REVERSAL\n\n"
        f"Original transaction:\n{json.dumps(original, indent=2)}\n\n"
        f"Alleged duplicate:\n{json.dumps(duplicate, indent=2)}\n\n"
        f"Verify all duplicate criteria and decide."
    )
    try:
        decision = _call_claude(DISPUTE_APPROVAL_PROMPT, payload)
        logger.info(
            f"Approver(dispute): {decision.get('decision')} "
            f"conf={decision.get('confidence')} — "
            f"{decision.get('audit_summary')}"
        )
        return decision
    except Exception as e:
        logger.error(f"Approver agent (dispute) error: {e}")
        return _reject(f"approver agent error: {e}")


# ── Loyalty review ────────────────────────────────────────────


def _fetch_uncredited(pan_masked: str) -> List[Dict]:
    r = execute_query(
        "SELECT transaction_id, amount, merchant_name, transaction_date, "
        "loyalty_points_earned, status, transaction_type, currency "
        "FROM transactions "
        "WHERE pan_masked = %s "
        "AND loyalty_points_earned > 0 "
        "AND loyalty_points_credited = FALSE",
        (pan_masked,),
    )
    return r.get("rows", [])


def _fetch_loyalty_account(pan_masked: str) -> Dict:
    r = execute_query(
        "SELECT account_id, pan_masked, points, tier, total_spent "
        "FROM loyalty_accounts WHERE pan_masked = %s",
        (pan_masked,),
    )
    return r["rows"][0] if r.get("rows") else {}


def review_loyalty_credit(pan_masked: str, points_to_add: int) -> Dict[str, Any]:
    """Review a loyalty credit request. Returns decision dict."""
    account = _fetch_loyalty_account(pan_masked)
    if not account:
        return _reject("PAN not enrolled in loyalty program")

    uncredited = _fetch_uncredited(pan_masked)
    if not uncredited:
        return _reject("no uncredited transactions for this PAN")

    expected_points = sum(int(t.get("loyalty_points_earned") or 0) for t in uncredited)
    if expected_points != int(points_to_add):
        return _reject(
            f"requested {points_to_add} points but DB shows {expected_points} uncredited"
        )

    payload = (
        f"Action: LOYALTY_CREDIT\n\n"
        f"Account: {json.dumps(account, indent=2)}\n\n"
        f"Uncredited transactions ({len(uncredited)}):\n"
        f"{json.dumps(uncredited, indent=2)}\n\n"
        f"Requested credit: {points_to_add} points\n"
        f"Verify eligibility and decide."
    )
    try:
        decision = _call_claude(LOYALTY_APPROVAL_PROMPT, payload)
        logger.info(
            f"Approver(loyalty): {decision.get('decision')} "
            f"conf={decision.get('confidence')} — "
            f"{decision.get('audit_summary')}"
        )
        return decision
    except Exception as e:
        logger.error(f"Approver agent (loyalty) error: {e}")
        return _reject(f"approver agent error: {e}")
