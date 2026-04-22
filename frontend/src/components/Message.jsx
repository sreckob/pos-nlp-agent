// Message.jsx
// Single chat message bubble — user or assistant

import ResultsTable from "./ResultsTable";
import SqlPanel from "./SqlPanel";

export default function Message({ msg }) {
  const isUser = msg.role === "user";

  return (
    <div style={{ ...styles.wrapper, justifyContent: isUser ? "flex-end" : "flex-start" }}>
      {!isUser && <div style={styles.avatar}>AI</div>}

      <div style={{ maxWidth: "80%" }}>
        <div style={isUser ? styles.userBubble : styles.assistantBubble}>
          {msg.content}
        </div>

        {!isUser && msg.sql && (
          <SqlPanel sql={msg.sql} />
        )}

        {!isUser && msg.rows && msg.rows.length > 0 && (
          <ResultsTable rows={msg.rows} rowCount={msg.rowCount} />
        )}

        <div style={styles.timestamp}>{msg.timestamp}</div>
      </div>

      {isUser && <div style={styles.avatarUser}>You</div>}
    </div>
  );
}

const styles = {
  wrapper: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
    marginBottom: 16
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: "50%",
    background: "#4f46e5",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    flexShrink: 0,
    marginTop: 2
  },
  avatarUser: {
    width: 32,
    height: 32,
    borderRadius: "50%",
    background: "#e5e7eb",
    color: "#374151",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    flexShrink: 0,
    marginTop: 2
  },
  userBubble: {
    background: "#4f46e5",
    color: "#fff",
    padding: "10px 14px",
    borderRadius: "18px 18px 4px 18px",
    fontSize: 14,
    lineHeight: 1.5
  },
  assistantBubble: {
    background: "#f3f4f6",
    color: "#111827",
    padding: "10px 14px",
    borderRadius: "18px 18px 18px 4px",
    fontSize: 14,
    lineHeight: 1.5
  },
  timestamp: {
    fontSize: 11,
    color: "#9ca3af",
    marginTop: 4,
    paddingLeft: 2
  }
};
