// Message.jsx — single chat bubble with path-specific panels

import ResultsTable from "./ResultsTable";
import SqlPanel     from "./SqlPanel";
import DisputeCard  from "./DisputeCard";
import LoyaltyPanel from "./LoyaltyPanel";

const ROLE_COLORS = {
  CARDHOLDER: "#2563EB",
  MERCHANT:   "#0D9488",
  DISPUTE:    "#DC2626",
  LOYALTY:    "#D97706",
};

export default function Message({ msg, onApprove, onReject, onCredit }) {
  const isUser = msg.role === "user";

  return (
    <div style={{ ...s.wrapper, justifyContent: isUser ? "flex-end" : "flex-start" }}>
      {!isUser && (
        <div style={{
          ...s.avatar,
          background: ROLE_COLORS[msg.agentRole] || "#1E40AF"
        }}>
          {roleIcon(msg.agentRole)}
        </div>
      )}

      <div style={{ maxWidth: "82%" }}>
        {/* Chat bubble */}
        <div style={isUser ? s.userBubble : s.agentBubble}>
          {msg.content}
        </div>

        {/* Agent-only extras */}
        {!isUser && (
          <>
            {/* Channel switch suggestion banner */}
            {msg.suggest_switch && msg.pending_role && (
              <div style={s.switchBanner}>
                <span style={s.switchIcon}>🔀</span>
                <span style={s.switchText}>
                  Suggested channel: <strong>{msg.pending_role}</strong>
                </span>
              </div>
            )}

            <SqlPanel sql={msg.sql} />

            {msg.rows && msg.rows.length > 0 && (
              <ResultsTable rows={msg.rows} rowCount={msg.rowCount || msg.rows.length} />
            )}

            {msg.agentRole === "DISPUTE" && msg.dispute_found && (
              <DisputeCard
                msg={msg}
                onApprove={onApprove}
                onReject={onReject}
              />
            )}

            {msg.agentRole === "LOYALTY" && msg.pan_enrolled && (
              <LoyaltyPanel
                msg={{ ...msg, pan_masked: msg.pan_masked }}
                onCredit={onCredit}
              />
            )}

            {msg.has_export && (
              <button style={s.exportBtn}>
                ⬇ Download Excel
              </button>
            )}
          </>
        )}

        <div style={s.timestamp}>{msg.timestamp}</div>
      </div>

      {isUser && <div style={s.userAvatar}>You</div>}
    </div>
  );
}

function roleIcon(role) {
  return { CARDHOLDER: "💳", MERCHANT: "🏪", DISPUTE: "⚠️", LOYALTY: "⭐" }[role] || "AI";
}

const s = {
  wrapper:    { display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 18 },
  avatar:     { width: 34, height: 34, borderRadius: "50%", color: "#fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 14, flexShrink: 0, marginTop: 2 },
  userAvatar: { width: 34, height: 34, borderRadius: "50%", background: "#E2E8F0",
                color: "#475569", display: "flex", alignItems: "center",
                justifyContent: "center", fontSize: 11, fontWeight: 700,
                flexShrink: 0, marginTop: 2 },
  userBubble: { background: "#1E40AF", color: "#fff", padding: "10px 14px",
                borderRadius: "18px 18px 4px 18px", fontSize: 14, lineHeight: 1.5 },
  agentBubble:{ background: "#F1F5F9", color: "#0F172A", padding: "10px 14px",
                borderRadius: "18px 18px 18px 4px", fontSize: 14, lineHeight: 1.5 },
  timestamp:  { fontSize: 11, color: "#CBD5E1", marginTop: 4, paddingLeft: 2 },
  exportBtn:  { marginTop: 8, padding: "6px 14px", borderRadius: 8,
                border: "1px solid #0D9488", background: "#F0FDFA",
                color: "#0D9488", fontWeight: 600, fontSize: 13, cursor: "pointer" },
  switchBanner: { display: "flex", alignItems: "center", gap: 8, marginTop: 8,
                  padding: "8px 12px", background: "#F5F3FF",
                  border: "1px solid #DDD6FE", borderRadius: 8 },
  switchIcon:   { fontSize: 14 },
  switchText:   { fontSize: 12, color: "#5B21B6" },
};
