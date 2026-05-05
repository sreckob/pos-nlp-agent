// api.js — WebSocket client for POS NLP Agent

const WS_BASE = process.env.REACT_APP_WS_URL || "ws://localhost:8000";

export function createWebSocket(sessionId, onMessage, onError, onClose) {
  const ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`);
  ws.onopen    = () => console.log("WebSocket connected:", sessionId);
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch {} };
  ws.onerror   = (e) => { if (onError) onError(e); };
  ws.onclose   = ()  => { if (onClose) onClose(); };
  return ws;
}

export function sendMessage(ws, message, imageData = null) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      message,
      image: imageData  // { base64, type } or null
    }));
    return true;
  }
  return false;
}

export async function getNewSessionId() {
  try {
    const res  = await fetch("/session/new");
    const data = await res.json();
    return data.session_id;
  } catch {
    return "session-" + Math.random().toString(36).slice(2, 10);
  }
}

// fetch helper that throws on HTTP errors (so callers can .catch them).
async function postJson(path, payload) {
  const res = await fetch(path, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || data.message || `HTTP ${res.status}`;
    const err = new Error(msg);
    err.status = res.status;
    err.data   = data;
    throw err;
  }
  return data;
}

// ── Customer-side: submit dispute / loyalty for ops review ────
export async function submitDispute(payload) {
  return postJson("/dispute/submit", payload);
}

export async function submitLoyalty(payload) {
  return postJson("/loyalty/submit", payload);
}

// ── Ops-side: queue + decide ──────────────────────────────────
export async function fetchOpsQueue() {
  const res = await fetch("/ops/queue");
  return res.json();
}

export async function fetchPendingDetail(approvalId) {
  const res = await fetch(`/ops/pending/${approvalId}`);
  return res.json();
}

export async function decideApproval(approvalId, decision, overrideSummary = null) {
  const res = await fetch("/ops/decide", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      approval_id:      approvalId,
      decision,
      override_summary: overrideSummary,
    }),
  });
  return res.json();
}
