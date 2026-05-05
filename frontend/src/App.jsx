// App.jsx — main chat application v3.0 (split-of-duties)
// Customer chat (left) + optional Ops Approver console (right, split-screen)

import { useState, useEffect, useRef, useCallback } from "react";
import RoleSelector  from "./components/RoleSelector";
import Message       from "./components/Message";
import ReceiptUpload from "./components/ReceiptUpload";
import OpsConsole    from "./components/OpsConsole";
import {
  createWebSocket, sendMessage, getNewSessionId,
  submitDispute, submitLoyalty,
} from "./api";

// ── Role metadata ─────────────────────────────────────────────
const ROLE_META = {
  CARDHOLDER: {
    label:   "Cardholder",
    color:   "#2563EB",
    bg:      "#EFF6FF",
    icon:    "💳",
    examples:[
      "Show my transactions for card ending in 4242",
      "Why was my card declined yesterday?",
      "Pokaži mi sve transakcije od prošle sedmice",
      "How many contactless payments did I make this month?",
    ],
  },
  MERCHANT: {
    label:   "Merchant",
    color:   "#0D9488",
    bg:      "#F0FDFA",
    icon:    "🏪",
    examples:[
      "Show all transactions on my terminals last week",
      "Which card brand is most used at my POS?",
      "Export declined transactions this month to Excel",
      "What was my total revenue yesterday?",
    ],
  },
  DISPUTE: {
    label:   "Dispute",
    color:   "#DC2626",
    bg:      "#FEF2F2",
    icon:    "⚠️",
    examples:[
      "I was charged twice at Maxi yesterday",
      "Duplo su mi naplatili u NIS Petrolu",
      "My card ending in 5555 was double-charged at NIS Petrol",
      "I have a receipt for a charge I didn't make",
    ],
  },
  LOYALTY: {
    label:   "Loyalty",
    color:   "#D97706",
    bg:      "#FFFBEB",
    icon:    "⭐",
    examples:[
      "My points were not added for my Lidl purchase",
      "Moji poeni nisu dodati za kupovinu u Maxi-ju",
      "Check loyalty points for card ending in 4242",
      "How many points do I have?",
    ],
  },
};

export default function App() {
  const [role,      setRole]      = useState(null);   // null = show role selector
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [isTyping,  setIsTyping]  = useState(false);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [receipt,   setReceipt]   = useState(null);   // for dispute path
  const [opsOpen,   setOpsOpen]   = useState(false);  // split-screen toggle

  const wsRef     = useRef(null);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  // ── WebSocket ────────────────────────────────────────────────
  const connect = useCallback(async (sid) => {
    if (wsRef.current) wsRef.current.close();

    wsRef.current = createWebSocket(
      sid,
      (data) => {
        if (data.type === "typing") { setIsTyping(true); return; }
        if (data.type === "response") {
          setIsTyping(false);
          setMessages(prev => [...prev, {
            id:                   Date.now(),
            role:                 "assistant",
            agentRole:            data.role,
            content:              data.message,
            sql:                  data.sql,
            rows:                 data.rows || [],
            rowCount:             data.row_count || 0,
            timestamp:            new Date().toLocaleTimeString(),
            // Switch suggestion
            suggest_switch:       data.suggest_switch,
            pending_role:         data.pending_role,
            // Dispute fields
            dispute_found:        data.dispute_found,
            reversal_recommended: data.reversal_recommended,
            original_tx_id:       data.original_tx_id,
            duplicate_tx_id:      data.duplicate_tx_id,
            confidence:           data.confidence,
            // Loyalty fields
            pan_enrolled:         data.pan_enrolled,
            missing_points:       data.missing_points,
            credit_recommended:   data.credit_recommended,
            pan_masked:           data.pan_masked,
            language:             data.language,
            has_export:           data.has_export,
          }]);
          // Auto-update role badge in UI if switch was confirmed
          if (data.role && data.role !== role && !data.suggest_switch) {
            setRole(data.role);
          }
          // Force reset to role selector on third strike
          if (data.force_reset) {
            setTimeout(() => {
              setRole(null);
              setMessages([]);
            }, 2500); // short delay so user reads the message first
          }
        }
        if (data.type === "error") {
          setIsTyping(false);
          setMessages(prev => [...prev, {
            id: Date.now(), role: "assistant",
            content: data.message,
            timestamp: new Date().toLocaleTimeString()
          }]);
        }
        if (data.type === "approval_decided") {
          const isApproved = data.decision === "APPROVED";
          const sr = data.language === "sr";
          let body;
          if (isApproved) {
            const ok = data.write_result?.message;
            body = (sr ? "✓ Vaš zahtev je odobren od strane operacija. " : "✓ Your request has been approved by operations. ")
                 + (ok || data.audit_summary || "");
          } else {
            body = (sr ? "✗ Vaš zahtev je odbijen od strane operacija. " : "✗ Your request was rejected by operations. ")
                 + (data.audit_summary || "");
          }
          setMessages(prev => [...prev, {
            id:        Date.now(),
            role:      "assistant",
            agentRole: data.approval_type,
            content:   body,
            timestamp: new Date().toLocaleTimeString(),
          }]);
        }
      },
      () => setConnected(false),
      () => setConnected(false)
    );
    setTimeout(() => setConnected(true), 300);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    getNewSessionId().then(sid => { setSessionId(sid); connect(sid); });
    return () => wsRef.current?.close();
  }, [connect]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  // ── Send message ─────────────────────────────────────────────
  function handleSend() {
    const text = input.trim();
    if (!text || !connected) return;

    // Build image data for WebSocket if receipt attached
    let imageData = null;
    if (receipt && receipt.base64) {
      // Strip the data URL prefix: "data:image/png;base64,..."
      const parts = receipt.base64.split(",");
      imageData = {
        base64: parts[1] || parts[0],
        type:   receipt.type || "image/png",
      };
    }

    setMessages(prev => [...prev, {
      id:        Date.now(),
      role:      "user",
      content:   text + (receipt ? ` 📎 ${receipt.filename}` : ""),
      timestamp: new Date().toLocaleTimeString()
    }]);

    sendMessage(wsRef.current, text, imageData);
    setInput("");
    setReceipt(null);
    inputRef.current?.focus();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  // ── Submit-for-review handlers (customer → ops queue) ───────
  async function handleSubmitDispute(originalTxId, duplicateTxId, msg) {
    try {
      await submitDispute({
        customer_session_id: sessionId,
        original_tx_id:      originalTxId,
        duplicate_tx_id:     duplicateTxId,
        pan_masked:          msg?.pan_masked || null,
        amount:              msg?.amount     || null,
        merchant_name:       msg?.merchant_name || null,
        language:            msg?.language || "en",
      });
      setMessages(prev => [...prev, {
        id:        Date.now(),
        role:      "assistant",
        agentRole: "DISPUTE",
        content:   "✓ Submitted to operations. You'll be notified when the review completes.",
        timestamp: new Date().toLocaleTimeString(),
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        id: Date.now(), role: "assistant", agentRole: "DISPUTE",
        content: "Could not submit for review: " + (err?.message || "unknown error"),
        timestamp: new Date().toLocaleTimeString(),
      }]);
    }
  }

  async function handleSubmitLoyalty(panMasked, points, msg) {
    try {
      await submitLoyalty({
        customer_session_id: sessionId,
        pan_masked:          panMasked,
        points_to_add:       points,
        language:            msg?.language || "en",
      });
      setMessages(prev => [...prev, {
        id:        Date.now(),
        role:      "assistant",
        agentRole: "LOYALTY",
        content:   "✓ Submitted to operations. You'll be notified when the review completes.",
        timestamp: new Date().toLocaleTimeString(),
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        id: Date.now(), role: "assistant", agentRole: "LOYALTY",
        content: "Could not submit for review: " + (err?.message || "unknown error"),
        timestamp: new Date().toLocaleTimeString(),
      }]);
    }
  }

  // ── New session ───────────────────────────────────────────────
  async function handleNewSession() {
    const sid = await getNewSessionId();
    setSessionId(sid);
    setMessages([]);
    setRole(null);   // back to role selector
    connect(sid);
  }

  // ── Role selection ────────────────────────────────────────────
  function handleRoleSelect(selectedRole) {
    setRole(selectedRole);
    // Send a silent first message to prime the router
    setTimeout(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        const greeting = {
          CARDHOLDER: "I am a cardholder and want to check my transactions",
          MERCHANT:   "I am a merchant and want to view my terminal transactions",
          DISPUTE:    "I am a cardholder and I have a dispute about a double charge",
          LOYALTY:    "I am a loyalty member and want to check my points",
        }[selectedRole];
        sendMessage(wsRef.current, greeting);
      }
    }, 400);
  }

  const meta = ROLE_META[role] || ROLE_META.CARDHOLDER;

  // ── Render: top bar + main flex row (customer | ops) ─────────
  return (
    <div style={styles.shell}>
      <div style={styles.topbar}>
        <span style={styles.brand}>POS NLP Agent</span>
        <button
          style={{
            ...styles.opsToggle,
            background: opsOpen ? "#0F172A" : "#fff",
            color:      opsOpen ? "#fff"    : "#0F172A",
          }}
          onClick={() => setOpsOpen(o => !o)}
          title="Operations approver console — reviews customer submissions"
        >
          {opsOpen ? "✕ Close Ops Console" : "🛡 Open Ops Console"}
        </button>
      </div>
      <div style={styles.row}>
        <div style={{ ...styles.col, flex: 1 }}>
          {!role
            ? <RoleSelector onSelect={handleRoleSelect} />
            : renderChat({
                meta, messages, isTyping, connected, sessionId, role,
                input, setInput, receipt, setReceipt, inputRef, bottomRef,
                handleSend, handleKeyDown, handleNewSession,
                handleSubmitDispute, handleSubmitLoyalty,
              })
          }
        </div>
        {opsOpen && (
          <div style={{ ...styles.col, width: "45%", flexShrink: 0 }}>
            <OpsConsole />
          </div>
        )}
      </div>
    </div>
  );
}

function renderChat({
  meta, messages, isTyping, connected, sessionId, role,
  input, setInput, receipt, setReceipt, inputRef, bottomRef,
  handleSend, handleKeyDown, handleNewSession,
  handleSubmitDispute, handleSubmitLoyalty,
}) {
  return (
    <div style={styles.app}>

      {/* Header */}
      <div style={{ ...styles.header, borderBottomColor: meta.color + "30" }}>
        <div style={{ ...styles.roleTag, background: meta.bg, color: meta.color }}>
          {meta.icon} {meta.label}
        </div>
        <div style={styles.headerCenter}>
          <span style={styles.appTitle}>Transaction Query Agent</span>
        </div>
        <div style={styles.headerRight}>
          <div style={{ ...styles.dot, background: connected ? "#22C55E" : "#EF4444" }} />
          <span style={styles.connLabel}>{connected ? "Live" : "Offline"}</span>
          <button style={styles.newBtn} onClick={handleNewSession}>New session</button>
        </div>
      </div>

      {/* Messages */}
      <div style={styles.messages}>
        {messages.length === 0 && (
          <div style={styles.empty}>
            <div style={{ ...styles.emptyIcon, background: meta.bg }}>{meta.icon}</div>
            <p style={styles.emptyTitle}>Ask about {meta.label.toLowerCase()} transactions</p>
            <div style={styles.examples}>
              {meta.examples.map((ex, i) => (
                <button key={i} style={styles.chip}
                  onClick={() => { setInput(ex); inputRef.current?.focus(); }}>
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <Message
            key={msg.id}
            msg={msg}
            onSubmitDispute={handleSubmitDispute}
            onSubmitLoyalty={handleSubmitLoyalty}
          />
        ))}

        {isTyping && (
          <div style={styles.typing}>
            <span style={styles.dot2} /><span style={styles.dot2} /><span style={styles.dot2} />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div style={styles.inputArea}>
        {role === "DISPUTE" && (
          <ReceiptUpload onUpload={setReceipt} />
        )}
        <div style={styles.inputRow}>
          <textarea
            ref={inputRef}
            style={styles.textarea}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              role === "DISPUTE"
                ? "Describe the double charge... / Opišite duplu naplatu..."
                : role === "LOYALTY"
                ? "Ask about your points... / Pitajte o poenima..."
                : role === "MERCHANT"
                ? "Ask about your terminals... / Pitajte o terminalima..."
                : "Ask about your transactions... / Pitajte o transakcijama..."
            }
            rows={1}
            disabled={!connected}
          />
          <button
            style={{
              ...styles.sendBtn,
              background: meta.color,
              opacity: (!input.trim() || !connected) ? 0.5 : 1
            }}
            onClick={handleSend}
            disabled={!input.trim() || !connected}
          >
            Send
          </button>
        </div>
      </div>

      <div style={styles.footer}>
        Session {sessionId?.slice(0, 8)}… · Press Enter to send · Serbian and English supported
      </div>
    </div>
  );
}

const styles = {
  shell: {
    display: "flex", flexDirection: "column", height: "100vh",
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    background: "#F8FAFC",
  },
  topbar: {
    background: "#0F172A", color: "#fff",
    padding: "8px 18px", display: "flex",
    justifyContent: "space-between", alignItems: "center",
    flexShrink: 0,
  },
  brand: { fontSize: 13, fontWeight: 700, letterSpacing: 0.3 },
  opsToggle: {
    padding: "6px 14px", borderRadius: 8, border: "1px solid #334155",
    fontWeight: 600, fontSize: 12, cursor: "pointer",
  },
  row: { flex: 1, display: "flex", overflow: "hidden" },
  col: { display: "flex", flexDirection: "column", overflow: "hidden", height: "100%" },
  app: {
    display: "flex", flexDirection: "column", height: "100%",
    fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    background: "#F8FAFC",
  },
  header: {
    background: "#fff", borderBottom: "1px solid",
    padding: "10px 20px", display: "flex",
    alignItems: "center", justifyContent: "space-between",
    flexShrink: 0, gap: 12,
  },
  roleTag: {
    padding: "4px 12px", borderRadius: 20, fontSize: 13,
    fontWeight: 600, whiteSpace: "nowrap",
  },
  headerCenter: { flex: 1, textAlign: "center" },
  appTitle:     { fontSize: 14, fontWeight: 600, color: "#334155" },
  headerRight:  { display: "flex", alignItems: "center", gap: 8 },
  dot:          { width: 8, height: 8, borderRadius: "50%" },
  connLabel:    { fontSize: 12, color: "#94A3B8" },
  newBtn: {
    padding: "5px 12px", borderRadius: 8, border: "1px solid #E2E8F0",
    background: "#fff", cursor: "pointer", fontSize: 12, color: "#475569",
  },
  messages: {
    flex: 1, overflowY: "auto", padding: "20px 24px",
    display: "flex", flexDirection: "column",
  },
  empty: {
    margin: "auto", textAlign: "center", paddingBottom: 40, maxWidth: 520,
  },
  emptyIcon: {
    width: 56, height: 56, borderRadius: 16, fontSize: 26,
    display: "flex", alignItems: "center", justifyContent: "center",
    margin: "0 auto 16px",
  },
  emptyTitle: { fontSize: 16, fontWeight: 600, color: "#334155", margin: "0 0 16px" },
  examples:   { display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" },
  chip: {
    padding: "7px 14px", borderRadius: 20, border: "1px solid #E2E8F0",
    background: "#fff", cursor: "pointer", fontSize: 12, color: "#475569",
    textAlign: "left",
  },
  typing: {
    display: "flex", gap: 4, padding: "10px 14px",
    background: "#F1F5F9", borderRadius: "18px 18px 18px 4px",
    width: "fit-content", marginBottom: 16,
  },
  dot2: {
    width: 7, height: 7, borderRadius: "50%", background: "#94A3B8",
    display: "inline-block", animation: "pulse 1.2s ease-in-out infinite",
  },
  inputArea: {
    background: "#fff", borderTop: "1px solid #E2E8F0",
    padding: "12px 20px", flexShrink: 0,
  },
  inputRow:  { display: "flex", gap: 8, marginTop: 8 },
  textarea: {
    flex: 1, padding: "10px 14px", borderRadius: 12,
    border: "1px solid #E2E8F0", fontSize: 14, resize: "none",
    fontFamily: "inherit", outline: "none", lineHeight: 1.5,
    background: "#F8FAFC",
  },
  sendBtn: {
    padding: "10px 20px", borderRadius: 12, border: "none",
    color: "#fff", fontWeight: 600, fontSize: 14, cursor: "pointer",
  },
  footer: {
    textAlign: "center", fontSize: 11, color: "#CBD5E1",
    padding: "6px 0 10px",
  },
};
