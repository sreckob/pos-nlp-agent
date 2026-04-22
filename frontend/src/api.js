// api.js
// WebSocket client — connects to FastAPI backend

const WS_BASE = process.env.REACT_APP_WS_URL || "ws://localhost:8000";

export function createWebSocket(sessionId, onMessage, onError, onClose) {
  const url = `${WS_BASE}/ws/${sessionId}`;
  const ws = new WebSocket(url);

  ws.onopen = () => {
    console.log("WebSocket connected:", sessionId);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error("Failed to parse message:", e);
    }
  };

  ws.onerror = (error) => {
    console.error("WebSocket error:", error);
    if (onError) onError(error);
  };

  ws.onclose = () => {
    console.log("WebSocket closed");
    if (onClose) onClose();
  };

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
    const res = await fetch("/session/new");
    const data = await res.json();
    return data.session_id;
  } catch {
    // fallback: generate client-side
    return "session-" + Math.random().toString(36).slice(2, 10);
  }
}
