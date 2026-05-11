"""
POS NLP Agent — FastAPI Backend v3.0 (split-of-duties)
=======================================================
Endpoints:
  GET  /health                          — health check
  GET  /session/new                     — generate new session ID
  GET  /session/{id}/history            — conversation history (debug)
  WS   /ws/{session_id}                 — WebSocket chat endpoint
  POST /dispute/submit                  — customer submits dispute for ops review
  POST /loyalty/submit                  — customer submits loyalty credit for review
  GET  /loyalty/balance/{pan_masked}    — get loyalty account balance (read)
  GET  /ops/queue                       — ops: list pending approvals
  GET  /ops/pending/{id}                — ops: detail + approver-agent recommendation
  POST /ops/decide                      — ops: approve or reject (gates write_ops)
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from db import init_pool, close_pool
from session import SessionStore
from agent import run_agent
from approval_agent import review_dispute, review_loyalty_credit
from executor import execute_query
import pending_store
from write_ops import (
    approve_dispute_reversal,
    reject_dispute,
    credit_loyalty_points,
    get_loyalty_balance,
)


def _is_uuid(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _tx_exists(tx_id: str) -> bool:
    if not _is_uuid(tx_id):
        return False
    r = execute_query(
        "SELECT 1 FROM transactions WHERE transaction_id = %s LIMIT 1",
        (str(tx_id),),
    )
    return bool(r.get("rows"))


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="POS NLP Query Agent", version="2.0.0")


def require_ops_key(x_ops_key: str = Header(...)):
    """FastAPI dependency — blocks /ops/* unless X-Ops-Key header matches OPS_API_KEY."""
    if not settings.OPS_API_KEY:
        raise HTTPException(status_code=500, detail="OPS_API_KEY not configured on server")
    if x_ops_key != settings.OPS_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid ops key")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_pool(settings.DATABASE_URL)

@app.on_event("shutdown")
async def shutdown():
    close_pool()


session_store = SessionStore()

# session_id → live WebSocket connection. Used by /ops/decide to push
# approval results back to the customer's chat in real time.
WS_CONNECTIONS: Dict[str, WebSocket] = {}


async def push_to_customer(session_id: str, payload: dict) -> bool:
    ws = WS_CONNECTIONS.get(session_id)
    if not ws:
        logger.info(f"No live WS for session {session_id[:8]} — push skipped")
        return False
    try:
        await ws.send_json(payload)
        return True
    except Exception as e:
        logger.warning(f"WS push failed for {session_id[:8]}: {e}")
        return False


# ── Health check ──────────────────────────────────────────────
@app.get("/")
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "pos-nlp-agent",
        "version": "2.0.0",
    }


# ── Session helpers ───────────────────────────────────────────
@app.get("/session/new")
async def new_session():
    session_id = str(uuid.uuid4())
    session_store.get_or_create(session_id)
    return {"session_id": session_id}


@app.get("/session/{session_id}/history")
async def get_history(session_id: str):
    session = session_store.get_or_create(session_id)
    return {
        "session_id": session_id,
        "role": session.get("role"),
        "language": session.get("language"),
        "turn_count": session.get("turn_count", 0),
        "history": session.get("history", []),
    }


# ── WebSocket chat endpoint ───────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    WS_CONNECTIONS[session_id] = websocket
    logger.info(f"Session connected: {session_id}")
    session_store.get_or_create(session_id)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
                user_message = data.get("message", "").strip()
                image_data = data.get("image")  # {base64, type} or None
                # Optional: client can force a role reset
                if data.get("reset_role"):
                    session_store.set_role(session_id, None)
            except json.JSONDecodeError:
                user_message = raw.strip()
                image_data = None

            if not user_message:
                continue

            logger.info(
                f"[{session_id}] User: {user_message[:80]}"
                + (" [+image]" if image_data else "")
            )

            # Typing indicator
            await websocket.send_json({"type": "typing", "session_id": session_id})

            try:
                result = await run_agent(
                    session_id=session_id,
                    user_message=user_message,
                    session_store=session_store,
                    image_data=image_data,
                )

                await websocket.send_json(
                    {
                        "type": "response",
                        "session_id": session_id,
                        "message": result["answer"],
                        "sql": result.get("sql"),
                        "rows": result.get("rows", []),
                        "row_count": result.get("row_count", 0),
                        "role": result.get("role"),
                        "language": result.get("language"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "suggest_switch": result.get("suggest_switch", False),
                        "switch_message": result.get("switch_message"),
                        "pending_role": result.get("pending_role"),
                        "force_reset": result.get("force_reset", False),
                        "mismatch_count": result.get("mismatch_count", 0),
                        "dispute_found": result.get("dispute_found", False),
                        "reversal_recommended": result.get(
                            "reversal_recommended", False
                        ),
                        "original_tx_id": result.get("original_tx_id"),
                        "duplicate_tx_id": result.get("duplicate_tx_id"),
                        "confidence": result.get("confidence", 0.0),
                        "missing_points": result.get("missing_points", 0),
                        "credit_recommended": result.get("credit_recommended", False),
                        "pan_enrolled": result.get("pan_enrolled", False),
                        "pan_masked": result.get("pan_masked"),
                        "has_export": result.get("export_file") is not None,
                    }
                )

                logger.info(
                    f"[{session_id}] role={result.get('role')} "
                    f"rows={result.get('row_count', 0)} "
                    f"latency={result.get('latency_ms')}ms"
                )

            except Exception as e:
                logger.error(f"[{session_id}] Agent error: {e}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "session_id": session_id,
                        "message": "Sorry, something went wrong. Please try again.",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

    except WebSocketDisconnect:
        logger.info(f"Session disconnected: {session_id}")
        session_store.clear(session_id)
    finally:
        WS_CONNECTIONS.pop(session_id, None)


# ── Request models ────────────────────────────────────────────
class DisputeSubmitRequest(BaseModel):
    customer_session_id: str
    original_tx_id: str
    duplicate_tx_id: str
    pan_masked: Optional[str] = None
    amount: Optional[float] = None
    merchant_name: Optional[str] = None
    language: str = "en"


class LoyaltySubmitRequest(BaseModel):
    customer_session_id: Optional[str] = None
    pan_masked: Optional[str] = None
    points_to_add: Optional[int] = None
    language: str = "en"


class OpsDecideRequest(BaseModel):
    approval_id: str
    decision: str  # "APPROVE" | "REJECT"
    override_summary: Optional[str] = None


# ── Customer-side submit endpoints ────────────────────────────
@app.post("/dispute/submit")
async def dispute_submit(req: DisputeSubmitRequest):
    """Customer submits dispute for ops review (does NOT execute reversal)."""
    # Reject hallucinated UUIDs at the boundary.
    if not _is_uuid(req.original_tx_id) or not _is_uuid(req.duplicate_tx_id):
        raise HTTPException(status_code=400, detail="invalid transaction IDs")
    if not _tx_exists(req.original_tx_id) or not _tx_exists(req.duplicate_tx_id):
        raise HTTPException(status_code=400, detail="transaction(s) not found in DB")
    if req.original_tx_id == req.duplicate_tx_id:
        raise HTTPException(
            status_code=400, detail="original and duplicate are the same row"
        )
    if not req.customer_session_id:
        raise HTTPException(status_code=400, detail="customer_session_id required")

    payload = {
        "original_tx_id": req.original_tx_id,
        "duplicate_tx_id": req.duplicate_tx_id,
        "pan_masked": req.pan_masked,
        "amount": req.amount,
        "merchant_name": req.merchant_name,
    }
    approval_id = pending_store.enqueue(
        type="DISPUTE",
        payload=payload,
        customer_session_id=req.customer_session_id,
        customer_language=req.language,
    )
    logger.info(
        f"Dispute submitted: id={approval_id[:8]} "
        f"original={req.original_tx_id[:8]} "
        f"duplicate={req.duplicate_tx_id[:8]}"
    )
    return {
        "submission_id": approval_id,
        "status": "PENDING",
        "message": "Submitted for operations review.",
    }


@app.post("/loyalty/submit")
async def loyalty_submit(req: LoyaltySubmitRequest):
    """Customer submits loyalty credit request for ops review."""
    if not req.customer_session_id:
        raise HTTPException(status_code=400, detail="customer_session_id required")
    if not req.pan_masked:
        raise HTTPException(
            status_code=400,
            detail="pan_masked missing — agent did not propagate it; ask the customer to repeat the card number",
        )
    if not req.points_to_add or req.points_to_add <= 0:
        raise HTTPException(status_code=400, detail="points_to_add must be > 0")

    payload = {
        "pan_masked": req.pan_masked,
        "points_to_add": req.points_to_add,
    }
    approval_id = pending_store.enqueue(
        type="LOYALTY",
        payload=payload,
        customer_session_id=req.customer_session_id,
        customer_language=req.language,
    )
    logger.info(
        f"Loyalty submitted: id={approval_id[:8]} "
        f"pan=...{req.pan_masked[-4:]} points={req.points_to_add}"
    )
    return {
        "submission_id": approval_id,
        "status": "PENDING",
        "message": "Submitted for operations review.",
    }


@app.get("/loyalty/balance/{pan_masked}")
async def loyalty_balance(pan_masked: str):
    """Get current loyalty account balance (read-only)."""
    return get_loyalty_balance(pan_masked)


# ── Ops endpoints ─────────────────────────────────────────────
@app.get("/ops/queue", dependencies=[Depends(require_ops_key)])
async def ops_queue():
    """List pending approvals for the ops console."""
    return {"pending": pending_store.list_pending()}


@app.get("/ops/pending/{approval_id}", dependencies=[Depends(require_ops_key)])
async def ops_pending_detail(approval_id: str):
    """
    Fetch one pending row + the approver agent's auto-recommendation.
    Recommendation is generated on first fetch and cached.
    """
    row = pending_store.get(approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="approval not found")

    if not row.get("agent_recommendation"):
        payload = (
            row["payload"]
            if isinstance(row["payload"], dict)
            else json.loads(row["payload"])
        )
        if row["type"] == "DISPUTE":
            recommendation = review_dispute(
                original_tx_id=payload["original_tx_id"],
                duplicate_tx_id=payload["duplicate_tx_id"],
            )
        elif row["type"] == "LOYALTY":
            recommendation = review_loyalty_credit(
                pan_masked=payload["pan_masked"],
                points_to_add=payload["points_to_add"],
            )
        else:
            raise HTTPException(status_code=400, detail=f"unknown type: {row['type']}")

        pending_store.cache_recommendation(approval_id, recommendation)
        row["agent_recommendation"] = recommendation

    return row


@app.post("/ops/decide", dependencies=[Depends(require_ops_key)])
async def ops_decide(req: OpsDecideRequest):
    """Ops decision: approve or reject. Approval triggers write_ops + customer push."""
    decision = req.decision.upper()
    if decision not in ("APPROVE", "REJECT"):
        raise HTTPException(
            status_code=400, detail="decision must be APPROVE or REJECT"
        )

    row = pending_store.get(req.approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="approval not found")
    if row["status"] != "PENDING":
        raise HTTPException(status_code=409, detail=f"already {row['status']}")

    payload = (
        row["payload"]
        if isinstance(row["payload"], dict)
        else json.loads(row["payload"])
    )
    rec = row.get("agent_recommendation") or {}
    audit = (
        req.override_summary or rec.get("audit_summary") or f"{decision} by ops_console"
    )
    write_result: dict = {"success": True}

    # On APPROVE — call the actual write_ops
    if decision == "APPROVE":
        if row["type"] == "DISPUTE":
            write_result = approve_dispute_reversal(
                original_tx_id=payload["original_tx_id"],
                duplicate_tx_id=payload["duplicate_tx_id"],
            )
        elif row["type"] == "LOYALTY":
            write_result = credit_loyalty_points(
                pan_masked=payload["pan_masked"],
                points_to_add=payload["points_to_add"],
            )

        if not write_result.get("success"):
            # Write failed — leave row PENDING so ops can retry / investigate
            return {
                "decision": "FAILED",
                "approval_id": req.approval_id,
                "write_result": write_result,
                "message": "Write operation failed — row left PENDING.",
            }

    # On REJECT for a dispute, mark the transactions as REJECTED in the
    # transactions table so they aren't actioned again. Loyalty rejection
    # is a no-op on transactions (points just stay uncredited).
    elif decision == "REJECT" and row["type"] == "DISPUTE":
        write_result = reject_dispute(
            duplicate_tx_id=payload["duplicate_tx_id"],
            original_tx_id=payload.get("original_tx_id"),
        )

    pending_store.mark_decided(
        approval_id=req.approval_id,
        decision="APPROVED" if decision == "APPROVE" else "REJECTED",
        audit_summary=audit,
    )

    # Push the result to the customer's chat (if WS still open)
    customer_session_id = row["customer_session_id"]
    customer_language = row.get("customer_language") or "en"
    pushed = await push_to_customer(
        customer_session_id,
        {
            "type": "approval_decided",
            "approval_id": req.approval_id,
            "approval_type": row["type"],
            "decision": "APPROVED" if decision == "APPROVE" else "REJECTED",
            "audit_summary": audit,
            "write_result": write_result,
            "language": customer_language,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

    return {
        "approval_id": req.approval_id,
        "decision": "APPROVED" if decision == "APPROVE" else "REJECTED",
        "audit_summary": audit,
        "write_result": write_result,
        "customer_notified": pushed,
    }
