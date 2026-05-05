// DisputeCard.jsx
// Shown when dispute investigator finds a duplicate charge.
// Customer clicks "Submit for review" → enqueues to ops console.

import { useState } from "react";

export default function DisputeCard({ msg, onSubmit }) {
  const { dispute_found, reversal_recommended, confidence,
          original_tx_id, duplicate_tx_id } = msg;

  const [busy, setBusy] = useState(false);

  if (!dispute_found) return null;

  const pct = Math.round((confidence || 0) * 100);

  async function handleClick() {
    setBusy(true);
    try {
      await onSubmit(original_tx_id, duplicate_tx_id, msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={s.card}>
      <div style={s.header}>
        <span style={s.icon}>⚠️</span>
        <span style={s.title}>Duplicate charge detected</span>
        <span style={{ ...s.badge, background: pct > 80 ? "#FEE2E2" : "#FEF3C7",
                       color: pct > 80 ? "#991B1B" : "#92400E" }}>
          {pct}% confidence
        </span>
      </div>

      {original_tx_id && (
        <div style={s.ids}>
          <div style={s.idRow}>
            <span style={s.idLabel}>Original</span>
            <code style={s.idVal}>{original_tx_id.slice(0, 8)}…</code>
          </div>
          {duplicate_tx_id && (
            <div style={s.idRow}>
              <span style={s.idLabel}>Duplicate</span>
              <code style={s.idVal}>{duplicate_tx_id.slice(0, 8)}…</code>
            </div>
          )}
        </div>
      )}

      {reversal_recommended && (
        <div style={s.actions}>
          <p style={s.rec}>
            Click Submit for review and operations will process the reversal.
          </p>
          <button style={s.approve} onClick={handleClick} disabled={busy}>
            {busy ? "Submitting…" : "Submit for review"}
          </button>
        </div>
      )}
    </div>
  );
}

const s = {
  card:    { background: "#FFF7ED", border: "1px solid #FED7AA", borderRadius: 10,
             padding: "14px 16px", marginTop: 8 },
  header:  { display: "flex", alignItems: "center", gap: 8, marginBottom: 10 },
  icon:    { fontSize: 16 },
  title:   { fontWeight: 600, fontSize: 13, color: "#9A3412", flex: 1 },
  badge:   { fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 10 },
  ids:     { marginBottom: 10 },
  idRow:   { display: "flex", gap: 8, alignItems: "center", marginBottom: 4 },
  idLabel: { fontSize: 11, color: "#9A3412", width: 64, fontWeight: 600 },
  idVal:   { fontSize: 11, color: "#334155", background: "#FEF3C7",
             padding: "1px 6px", borderRadius: 4 },
  rec:     { fontSize: 12, color: "#9A3412", margin: "0 0 10px 0" },
  actions: {},
  approve: { padding: "8px 18px", borderRadius: 8, border: "none",
             background: "#9A3412", color: "#fff", fontWeight: 600,
             fontSize: 13, cursor: "pointer" },
  submitted: { fontSize: 12, color: "#15803D", background: "#DCFCE7",
               padding: "8px 12px", borderRadius: 8, marginTop: 8 },
};
