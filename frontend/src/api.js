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

export function sendMessage(ws, message) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ message }));
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
