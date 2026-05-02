"""
POS NLP Agent — FastAPI Backend v2.1
=====================================
Endpoints:
  GET  /health                          — health check
  GET  /session/new                     — generate new session ID
  GET  /session/{id}/history            — conversation history (debug)
  WS   /ws/{session_id}                 — WebSocket chat endpoint
  POST /dispute/approve                 — approve dispute reversal
  POST /dispute/reject                  — reject dispute claim
  POST /loyalty/credit                  — credit missing loyalty points
  GET  /loyalty/balance/{pan_masked}    — get loyalty account balance
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from session import SessionStore
from agent import run_agent
from write_ops import (
    approve_dispute_reversal,
    reject_dispute,
    credit_loyalty_points,
    get_loyalty_balance,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="POS NLP Query Agent",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_store = SessionStore()

# ── Health check ──────────────────────────────────────────────
@app.get("/")
@app.get("/health")
async def health():
    return {
        "status":    "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service":   "pos-nlp-agent",
        "version":   "2.0.0"
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
        "session_id":  session_id,
        "role":        session.get("role"),
        "language":    session.get("language"),
        "turn_count":  session.get("turn_count", 0),
        "history":     session.get("history", [])
    }

# ── WebSocket chat endpoint ───────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"Session connected: {session_id}")
    session_store.get_or_create(session_id)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data         = json.loads(raw)
                user_message = data.get("message", "").strip()
                image_data   = data.get("image")  # {base64, type} or None
                # Optional: client can force a role reset
                if data.get("reset_role"):
                    session_store.set_role(session_id, None)
            except json.JSONDecodeError:
                user_message = raw.strip()
                image_data   = None

            if not user_message:
                continue

            logger.info(
                f"[{session_id}] User: {user_message[:80]}"
                + (" [+image]" if image_data else "")
            )

            # Typing indicator
            await websocket.send_json({
                "type":       "typing",
                "session_id": session_id
            })

            try:
                result = await run_agent(
                    session_id    = session_id,
                    user_message  = user_message,
                    session_store = session_store,
                    image_data    = image_data,
                )

                await websocket.send_json({
                    "type":                 "response",
                    "session_id":           session_id,
                    "message":              result["answer"],
                    "sql":                  result.get("sql"),
                    "rows":                 result.get("rows", []),
                    "row_count":            result.get("row_count", 0),
                    "role":                 result.get("role"),
                    "language":             result.get("language"),
                    "timestamp":            datetime.utcnow().isoformat(),
                    "suggest_switch":       result.get("suggest_switch", False),
                    "switch_message":       result.get("switch_message"),
                    "pending_role":         result.get("pending_role"),
                    "force_reset":          result.get("force_reset", False),
                    "mismatch_count":       result.get("mismatch_count", 0),
                    "dispute_found":        result.get("dispute_found", False),
                    "reversal_recommended": result.get("reversal_recommended", False),
                    "original_tx_id":       result.get("original_tx_id"),
                    "duplicate_tx_id":      result.get("duplicate_tx_id"),
                    "confidence":           result.get("confidence", 0.0),
                    "missing_points":       result.get("missing_points", 0),
                    "credit_recommended":   result.get("credit_recommended", False),
                    "pan_enrolled":         result.get("pan_enrolled", False),
                    "pan_masked":           result.get("pan_masked"),
                    "has_export":           result.get("export_file") is not None,
                })

                logger.info(
                    f"[{session_id}] role={result.get('role')} "
                    f"rows={result.get('row_count', 0)} "
                    f"latency={result.get('latency_ms')}ms"
                )

            except Exception as e:
                logger.error(f"[{session_id}] Agent error: {e}")
                await websocket.send_json({
                    "type":       "error",
                    "session_id": session_id,
                    "message":    "Sorry, something went wrong. Please try again.",
                    "timestamp":  datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        logger.info(f"Session disconnected: {session_id}")
        session_store.clear(session_id)


# ── Request models ────────────────────────────────────────────
class DisputeApproveRequest(BaseModel):
    original_tx_id:  str
    duplicate_tx_id: str

class DisputeRejectRequest(BaseModel):
    duplicate_tx_id: str
    original_tx_id:  str = None

class LoyaltyCreditRequest(BaseModel):
    pan_masked:    str
    points_to_add: int

# ── Dispute endpoints ─────────────────────────────────────────
@app.post("/dispute/approve")
async def dispute_approve(req: DisputeApproveRequest):
    """Approve a dispute reversal — marks duplicate as REVERSED."""
    logger.info(
        f"Dispute approval: "
        f"original={req.original_tx_id[:8]} "
        f"duplicate={req.duplicate_tx_id[:8]}"
    )
    result = approve_dispute_reversal(
        original_tx_id  = req.original_tx_id,
        duplicate_tx_id = req.duplicate_tx_id
    )
    return result

@app.post("/dispute/reject")
async def dispute_reject(req: DisputeRejectRequest):
    """Reject a dispute claim."""
    logger.info(f"Dispute rejection: {req.duplicate_tx_id[:8]}")
    result = reject_dispute(
        duplicate_tx_id = req.duplicate_tx_id,
        original_tx_id  = req.original_tx_id
    )
    return result

# ── Loyalty endpoints ─────────────────────────────────────────
@app.post("/loyalty/credit")
async def loyalty_credit(req: LoyaltyCreditRequest):
    """Credit missing loyalty points to an account."""
    logger.info(
        f"Loyalty credit: "
        f"pan=...{req.pan_masked[-4:]} "
        f"points={req.points_to_add}"
    )
    result = credit_loyalty_points(
        pan_masked    = req.pan_masked,
        points_to_add = req.points_to_add
    )
    return result

@app.get("/loyalty/balance/{pan_masked}")
async def loyalty_balance(pan_masked: str):
    """Get current loyalty account balance."""
    return get_loyalty_balance(pan_masked)

