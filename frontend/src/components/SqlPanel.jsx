// SqlPanel.jsx — collapsible generated SQL display
import { useState } from "react";

export default function SqlPanel({ sql }) {
  const [open, setOpen] = useState(false);
  if (!sql) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <button
        style={{ background: "none", border: "none", color: "#94A3B8",
                 fontSize: 11, cursor: "pointer", padding: 0, fontFamily: "monospace" }}
        onClick={() => setOpen(o => !o)}
      >
        {open ? "▾" : "▸"} generated SQL
      </button>
      {open && (
        <pre style={{ background: "#0F172A", color: "#94A3B8", padding: "10px 14px",
                      borderRadius: 8, fontSize: 11, overflowX: "auto", marginTop: 6,
                      lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {sql}
        </pre>
      )}
    </div>
  );
}
