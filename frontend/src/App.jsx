// App.jsx
// Main chat application

import { useState, useEffect, useRef, useCallback } from "react";
import Message from "./components/Message";
import { createWebSocket, sendMessage, getNewSessionId } from "./api";

export default function App() {
  const [messages,   setMessages]   = useState([]);
  const [input,      setInput]      = useState("");
  const [isTyping,   setIsTyping]   = useState(false);
  const [connected,  setConnected]  = useState(false);
  const [sessionId,  setSessionId]  = useState(null);

  const wsRef      = useRef(null);
  const bottomRef  = useRef(null);
  const inputRef   = useRef(null);

  // ── Initialise session and WebSocket ──────────────────────
  const connect = useCallback(async (sid) => {
    if (wsRef.current) wsRef.current.close();

    wsRef.current = createWebSocket(
      sid,
      // onMessage
      (data) => {
        if (data.type === "typing") {
          setIsTyping(true);
          return;
        }
        if (data.type === "response") {
          setIsTyping(false);
          setMessages(prev => [...prev, {
            id:        Date.now(),
            role:      "assistant",
            content:   data.message,
            sql:       data.sql,
            rows:      data.rows || [],
            rowCount:  data.row_count || 0,
            timestamp: new Date().toLocaleTimeString()
          }]);
        }
        if (data.type === "error") {
          setIsTyping(false);
          setMessages(prev => [...prev, {
            id:        Date.now(),
            role:      "assistant",
            content:   data.message,
            timestamp: new Date().toLocaleTimeString()
          }]);
        }
      },
      // onError
      () => setConnected(false),
      // onClose
      () => setConnected(false)
    );

    // Give WS a moment to open
    setTimeout(() => setConnected(true), 300);
  }, []);

  useEffect(() => {
    getNewSessionId().then(sid => {
      setSessionId(sid);
      connect(sid);
    });
    return () => wsRef.current?.close();
  }, [connect]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  // ── Send message ───────────────────────────────────────────
  function handleSend() {
    const text = input.trim();
    if (!text || !connected) return;

    setMessages(prev => [...prev, {
      id:        Date.now(),
      role:      "user",
      content:   text,
      timestamp: new Date().toLocaleTimeString()
    }]);

    sendMessage(wsRef.current, text);
    setInput("");
    inputRef.current?.focus();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  // ── New session ────────────────────────────────────────────
  async function handleNewSession() {
    const sid = await getNewSessionId();
    setSessionId(sid);
    setMessages([]);
    connect(sid);
  }

  // ── Render ─────────────────────────────────────────────────
  return (
    <div style={styles.app}>

      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <div style={styles.logo}>POS</div>
          <div>
            <div style={styles.title}>Transaction Query Agent</div>
            <div style={styles.subtitle}>
              Ask about payment transactions in Serbian or English
            </div>
          </div>
        </div>
        <div style={styles.headerRight}>
          <div style={{ ...styles.dot, background: connected ? "#22c55e" : "#ef4444" }} />
          <span style={styles.status}>{connected ? "Connected" : "Disconnected"}</span>
          <button style={styles.newBtn} onClick={handleNewSession}>
            New session
          </button>
        </div>
      </div>

      {/* Messages */}
      <div style={styles.messages}>
        {messages.length === 0 && (
          <div style={styles.empty}>
            <div style={styles.emptyTitle}>Start a conversation</div>
            <div style={styles.examples}>
              <ExampleChip text="Show declined transactions above 5000 RSD" onSend={t => { setInput(t); setTimeout(handleSend, 0); }} />
              <ExampleChip text="Pokaži Visa beskontaktne transakcije od juče" onSend={t => { setInput(t); setTimeout(handleSend, 0); }} />
              <ExampleChip text="Which terminal processed the most transactions?" onSend={t => { setInput(t); setTimeout(handleSend, 0); }} />
              <ExampleChip text="Koliko odbijenih transakcija je bilo prošle sedmice?" onSend={t => { setInput(t); setTimeout(handleSend, 0); }} />
            </div>
          </div>
        )}

        {messages.map(msg => (
          <Message key={msg.id} msg={msg} />
        ))}

        {isTyping && (
          <div style={styles.typing}>
            <div style={styles.typingDot} />
            <div style={styles.typingDot} />
            <div style={styles.typingDot} />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={styles.inputArea}>
        <textarea
          ref={inputRef}
          style={styles.textarea}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about transactions... / Pitajte o transakcijama..."
          rows={1}
          disabled={!connected}
        />
        <button
          style={{ ...styles.sendBtn, opacity: (!input.trim() || !connected) ? 0.5 : 1 }}
          onClick={handleSend}
          disabled={!input.trim() || !connected}
        >
          Send
        </button>
      </div>

      <div style={styles.footer}>
        Session: {sessionId?.slice(0, 8)}...  ·  Press Enter to send
      </div>
    </div>
  );
}

function ExampleChip({ text, onSend }) {
  return (
    <button style={styles.chip} onClick={() => onSend(text)}>
      {text}
    </button>
  );
}

// ── Styles ─────────────────────────────────────────────────────
const styles = {
  app: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    background: "#f9fafb"
  },
  header: {
    background: "#fff",
    borderBottom: "1px solid #e5e7eb",
    padding: "12px 24px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexShrink: 0
  },
  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: 12
  },
  logo: {
    width: 40,
    height: 40,
    borderRadius: 10,
    background: "#4f46e5",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 800,
    fontSize: 14,
    letterSpacing: 1
  },
  title: {
    fontWeight: 700,
    fontSize: 16,
    color: "#111827"
  },
  subtitle: {
    fontSize: 12,
    color: "#6b7280",
    marginTop: 1
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: 8
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%"
  },
  status: {
    fontSize: 13,
    color: "#6b7280"
  },
  newBtn: {
    marginLeft: 8,
    padding: "6px 14px",
    borderRadius: 8,
    border: "1px solid #e5e7eb",
    background: "#fff",
    cursor: "pointer",
    fontSize: 13,
    color: "#374151"
  },
  messages: {
    flex: 1,
    overflowY: "auto",
    padding: "24px",
    display: "flex",
    flexDirection: "column"
  },
  empty: {
    margin: "auto",
    textAlign: "center",
    paddingBottom: 40
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: 600,
    color: "#374151",
    marginBottom: 16
  },
  examples: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    justifyContent: "center",
    maxWidth: 600
  },
  chip: {
    padding: "8px 14px",
    borderRadius: 20,
    border: "1px solid #e5e7eb",
    background: "#fff",
    cursor: "pointer",
    fontSize: 13,
    color: "#4f46e5",
    transition: "background 0.15s"
  },
  typing: {
    display: "flex",
    gap: 4,
    padding: "10px 14px",
    background: "#f3f4f6",
    borderRadius: "18px 18px 18px 4px",
    width: "fit-content",
    marginBottom: 16
  },
  typingDot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "#9ca3af",
    animation: "pulse 1.2s ease-in-out infinite"
  },
  inputArea: {
    display: "flex",
    gap: 8,
    padding: "12px 24px",
    background: "#fff",
    borderTop: "1px solid #e5e7eb",
    flexShrink: 0
  },
  textarea: {
    flex: 1,
    padding: "10px 14px",
    borderRadius: 12,
    border: "1px solid #e5e7eb",
    fontSize: 14,
    resize: "none",
    fontFamily: "inherit",
    outline: "none",
    lineHeight: 1.5
  },
  sendBtn: {
    padding: "10px 20px",
    borderRadius: 12,
    border: "none",
    background: "#4f46e5",
    color: "#fff",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer"
  },
  footer: {
    textAlign: "center",
    fontSize: 11,
    color: "#9ca3af",
    padding: "6px 0 10px"
  }
};
