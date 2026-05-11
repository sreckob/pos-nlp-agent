// api.js — WebSocket + REST client for POS NLP Agent

const WS_BASE = process.env.REACT_APP_WS_URL || "ws://localhost:8000";

// REST base — in dev (no env var), use "" so relative paths go through
// CRA's package.json proxy. In prod, derive from WS_BASE so we don't
// need a separate env var on Vercel.
const API_BASE = process.env.REACT_APP_API_URL
  || (process.env.REACT_APP_WS_URL
        ? process.env.REACT_APP_WS_URL
            .replace(/^wss:\/\//, "https://")
            .replace(/^ws:\/\//,  "http://")
        : "");

function url(path) { return API_BASE + path; }

// Ops console key — set REACT_APP_OPS_KEY in .env (local) and Vercel env vars (prod)
const OPS_KEY = process.env.REACT_APP_OPS_KEY || "";
function opsHeaders() {
  return { "Content-Type": "application/json", "x-ops-key": OPS_KEY };
}

export function createWebSocket(sessionId, onMessage, onOpen, onError, onClose) {
  const ws = new WebSocket(`${WS_BASE}/ws/${sessionId}`);
  ws.onopen    = () => { if (onOpen)  onOpen();    };
  ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch {} };
  ws.onerror   = (e) => { if (onError) onError(e); };
  ws.onclose   = ()  => { if (onClose) onClose();  };
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
    const res  = await fetch(url("/session/new"));
    const data = await res.json();
    return data.session_id;
  } catch {
    return "session-" + crypto.randomUUID().slice(0, 8);
  }
}

// fetch helper that throws on HTTP errors (so callers can .catch them).
async function postJson(path, payload) {
  const res = await fetch(url(path), {
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
  const res = await fetch(url("/ops/queue"), { headers: opsHeaders() });
  return res.json();
}

export async function fetchPendingDetail(approvalId) {
  const res = await fetch(url(`/ops/pending/${approvalId}`), { headers: opsHeaders() });
  return res.json();
}

export async function decideApproval(approvalId, decision, overrideSummary = null) {
  const res = await fetch(url("/ops/decide"), {
    method:  "POST",
    headers: opsHeaders(),
    body:    JSON.stringify({
      approval_id:      approvalId,
      decision,
      override_summary: overrideSummary,
    }),
  });
  return res.json();
}
