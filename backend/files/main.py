"""
POS NLP Agent — FastAPI Backend
================================
Endpoints:
  GET  /           — health check
  GET  /health     — health check JSON
  WS   /ws/{session_id}  — WebSocket chat endpoint

Run locally:
    uvicorn main:app --reload --port 8000
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from session import SessionStore
from agent import run_agent

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="POS NLP Query Agent",
    description="Natural language query agent for POS payment transactions",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
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
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "pos-nlp-agent"
    }

# ── WebSocket chat endpoint ───────────────────────────────────
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"Session connected: {session_id}")

    # Initialise session if new
    session_store.get_or_create(session_id)

    try:
        while True:
            # Receive message from client
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
                user_message = data.get("message", "").strip()
            except json.JSONDecodeError:
                user_message = raw.strip()

            if not user_message:
                continue

            logger.info(f"[{session_id}] User: {user_message}")

            # Send typing indicator
            await websocket.send_json({
                "type": "typing",
                "session_id": session_id
            })

            # Run the agent
            try:
                result = await run_agent(
                    session_id=session_id,
                    user_message=user_message,
                    session_store=session_store
                )

                # Send response back to client
                await websocket.send_json({
                    "type": "response",
                    "session_id": session_id,
                    "message": result["answer"],
                    "sql": result.get("sql"),
                    "rows": result.get("rows", []),
                    "row_count": result.get("row_count", 0),
                    "timestamp": datetime.utcnow().isoformat()
                })

                logger.info(
                    f"[{session_id}] Agent responded | "
                    f"rows={result.get('row_count', 0)} | "
                    f"latency={result.get('latency_ms')}ms"
                )

            except Exception as e:
                logger.error(f"[{session_id}] Agent error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "session_id": session_id,
                    "message": "Sorry, something went wrong processing your request. Please try again.",
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        logger.info(f"Session disconnected: {session_id}")
        session_store.clear(session_id)


# ── New session helper endpoint ───────────────────────────────
@app.get("/session/new")
async def new_session():
    """Generate a new session ID for the client."""
    session_id = str(uuid.uuid4())
    session_store.get_or_create(session_id)
    return {"session_id": session_id}


@app.get("/session/{session_id}/history")
async def get_history(session_id: str):
    """Return conversation history for a session (for debugging)."""
    session = session_store.get_or_create(session_id)
    return {
        "session_id": session_id,
        "turn_count": len(session["history"]),
        "history": session["history"]
    }
