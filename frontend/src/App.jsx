// App.jsx — main chat application v3.1
// Slimmed: WS lifecycle + messages array now live in useChatSocket;
// the textarea state lives in MessageInput. App composes layout +
// orchestrates the dispute/loyalty submit flows.

import { useState, useEffect, useRef, useCallback } from "react";
import RoleSelector  from "./components/RoleSelector";
import MessageList   from "./components/MessageList";
import ReceiptUpload from "./components/ReceiptUpload";
import OpsConsole    from "./components/OpsConsole";
import MessageInput  from "./components/MessageInput";
import { submitDispute, submitLoyalty } from "./api";
import { useChatSocket } from "./hooks/useChatSocket";

// ── Role metadata ─────────────────────────────────────────────
const ROLE_META = {
  CARDHOLDER: { label: "Cardholder", color: "#2563EB", bg: "#EFF6FF", icon: "💳" },
  MERCHANT:   { label: "Merchant",   color: "#0D9488", bg: "#F0FDFA", icon: "🏪" },
  DISPUTE:    { label: "Dispute",    color: "#DC2626", bg: "#FEF2F2", icon: "⚠️" },
  LOYALTY:    { label: "Loyalty",    color: "#D97706", bg: "#FFFBEB", icon: "⭐" },
};

// Bilingual welcome messages injected directly into chat on role select.
// No LLM call — language-neutral, clearly states required fields per path.
const WELCOME_MESSAGES = {
  CARDHOLDER:
    "Welcome to the Cardholder channel.\n" +
    "To look up your transactions, please provide your card's last 4 digits.\n\n" +
    "Dobrodošli na kanal za kartičare.\n" +
    "Za pretragu transakcija navedite poslednje 4 cifre vaše kartice.",

  MERCHANT:
    "Welcome to the Merchant channel.\n" +
    "Please identify yourself with your merchant name or terminal ID.\n\n" +
    "Dobrodošli na kanal za trgovce.\n" +
    "Navedite naziv vašeg poslovnog mesta ili ID terminala.",

  DISPUTE:
    "Welcome to the Dispute channel.\n" +
    "To investigate a potential double charge, I will need:\n" +
    "  • Card last 4 digits\n" +
    "  • Merchant name\n" +
    "  • Amount charged\n" +
    "  • Approximate date\n" +
    "You can also attach a receipt image.\n\n" +
    "Dobrodošli na kanal za sporove.\n" +
    "Za istragu duplog zaduženja potrebno mi je:\n" +
    "  • Poslednje 4 cifre kartice\n" +
    "  • Naziv prodavca\n" +
    "  • Iznos zaduženja\n" +
    "  • Približan datum\n" +
    "Možete priložiti i sliku računa.",

  LOYALTY:
    "Welcome to the Loyalty channel.\n" +
    "Please provide your full masked card number (e.g. 411111******4242) " +
    "or your card's last 4 digits to check your points.\n\n" +
    "Dobrodošli na kanal za lojalnost.\n" +
    "Navedite pun maskirani broj kartice (npr. 411111******4242) " +
    "ili poslednje 4 cifre kartice da biste proverili poene.",
};

const PLACEHOLDERS = {
  DISPUTE:    "Describe the double charge... / Opišite duplu naplatu...",
  LOYALTY:    "Ask about your points... / Pitajte o poenima...",
  MERCHANT:   "Ask about your terminals... / Pitajte o terminalima...",
  CARDHOLDER: "Ask about your transactions... / Pitajte o transakcijama...",
};

export default function App() {
  const {
    messages, isTyping, connected, sessionId, role,
    setRole, sendChat, addMessage, newSession,
  } = useChatSocket();

  const [receipt, setReceipt] = useState(null);   // dispute path
  const [opsOpen, setOpsOpen] = useState(false);  // split-screen toggle

  const inputRef  = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  // ── User-typed turn ──────────────────────────────────────────
  function handleSend(text) {
    if (!connected) return;

    let imageData = null;
    if (receipt && receipt.base64) {
      const parts = receipt.base64.split(",");
      imageData = {
        base64: parts[1] || parts[0],
        type:   receipt.type || "image/png",
      };
    }

    addMessage({
      role:    "user",
      content: text + (receipt ? ` 📎 ${receipt.filename}` : ""),
    });
    sendChat(text, imageData);
    setReceipt(null);
  }

  // ── Role selection ───────────────────────────────────────────
  // Inject a static welcome immediately (no LLM call, no language ambiguity).
  // The router detects the channel from the user's first real message.
  function handleRoleSelect(selectedRole) {
    setRole(selectedRole);
    addMessage({
      role:      "assistant",
      agentRole: selectedRole,
      content:   WELCOME_MESSAGES[selectedRole],
    });
  }

  // ── Submit-for-review handlers ───────────────────────────────
  // useCallback so MessageList's React.memo actually skips re-renders
  // when these handler references would otherwise change every render.
  const handleSubmitDispute = useCallback(async (originalTxId, duplicateTxId, msg) => {
    try {
      await submitDispute({
        customer_session_id: sessionId,
        original_tx_id:      originalTxId,
        duplicate_tx_id:     duplicateTxId,
        pan_masked:          msg?.pan_masked    || null,
        amount:              msg?.amount        || null,
        merchant_name:       msg?.merchant_name || null,
        language:            msg?.language      || "en",
      });
      addMessage({
        role: "assistant", agentRole: "DISPUTE",
        content: "✓ Submitted to operations. You'll be notified when the review completes.",
      });
    } catch (err) {
      addMessage({
        role: "assistant", agentRole: "DISPUTE",
        content: "Could not submit for review: " + (err?.message || "unknown error"),
      });
    }
  }, [sessionId, addMessage]);

  const handleSubmitLoyalty = useCallback(async (panMasked, points, msg) => {
    try {
      await submitLoyalty({
        customer_session_id: sessionId,
        pan_masked:          panMasked,
        points_to_add:       points,
        language:            msg?.language || "en",
      });
      addMessage({
        role: "assistant", agentRole: "LOYALTY",
        content: "✓ Submitted to operations. You'll be notified when the review completes.",
      });
    } catch (err) {
      addMessage({
        role: "assistant", agentRole: "LOYALTY",
        content: "Could not submit for review: " + (err?.message || "unknown error"),
      });
    }
  }, [sessionId, addMessage]);

  const meta = ROLE_META[role] || ROLE_META.CARDHOLDER;

  // ── Render ───────────────────────────────────────────────────
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
          {!role ? (
            <RoleSelector onSelect={handleRoleSelect} />
          ) : (
            <ChatView
              meta={meta}
              messages={messages}
              isTyping={isTyping}
              connected={connected}
              sessionId={sessionId}
              role={role}
              receipt={receipt}
              setReceipt={setReceipt}
              inputRef={inputRef}
              bottomRef={bottomRef}
              onSend={handleSend}
              onNewSession={newSession}
              onSubmitDispute={handleSubmitDispute}
              onSubmitLoyalty={handleSubmitLoyalty}
            />
          )}
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

// ── ChatView — header + message list + input ─────────────────
function ChatView({
  meta, messages, isTyping, connected, sessionId, role,
  receipt, setReceipt, inputRef, bottomRef,
  onSend, onNewSession, onSubmitDispute, onSubmitLoyalty,
}) {
  return (
    <div style={styles.app}>
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
          <button style={styles.newBtn} onClick={onNewSession}>New session</button>
        </div>
      </div>

      <div style={styles.messages}>
        <MessageList
          messages={messages}
          isTyping={isTyping}
          onSubmitDispute={onSubmitDispute}
          onSubmitLoyalty={onSubmitLoyalty}
        />
        <div ref={bottomRef} />
      </div>

      <div style={styles.inputArea}>
        {role === "DISPUTE" && <ReceiptUpload onUpload={setReceipt} />}
        <MessageInput
          ref={inputRef}
          onSend={onSend}
          placeholder={PLACEHOLDERS[role] || PLACEHOLDERS.CARDHOLDER}
          accentColor={meta.color}
          disabled={!connected}
        />
      </div>

      <div style={styles.footer}>
        Session {sessionId?.slice(0, 8)}… · Press Enter to send · Serbian and English supported
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────
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
  inputArea: {
    background: "#fff", borderTop: "1px solid #E2E8F0",
    padding: "12px 20px", flexShrink: 0,
  },
  footer: {
    textAlign: "center", fontSize: 11, color: "#CBD5E1",
    padding: "6px 0 10px",
  },
};
