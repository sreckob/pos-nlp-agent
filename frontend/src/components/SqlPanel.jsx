// SqlPanel.jsx
// Collapsible panel showing the generated SQL query

import { useState } from "react";

export default function SqlPanel({ sql }) {
  const [open, setOpen] = useState(false);

  if (!sql) return null;

  return (
    <div style={styles.wrapper}>
      <button style={styles.toggle} onClick={() => setOpen(o => !o)}>
        {open ? "▾" : "▸"} SQL query
      </button>
      {open && (
        <pre style={styles.code}>{sql}</pre>
      )}
    </div>
  );
}

const styles = {
  wrapper: {
    marginTop: 6
  },
  toggle: {
    background: "none",
    border: "none",
    color: "#6b7280",
    fontSize: 12,
    cursor: "pointer",
    padding: 0,
    fontFamily: "monospace"
  },
  code: {
    background: "#1e1e2e",
    color: "#cdd6f4",
    padding: "10px 14px",
    borderRadius: 8,
    fontSize: 12,
    overflowX: "auto",
    marginTop: 6,
    lineHeight: 1.6,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word"
  }
};
