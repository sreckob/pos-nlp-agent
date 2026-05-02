// DisputeCard.jsx
// Shown when dispute agent finds a duplicate charge
// Presents recommendation with Approve / Reject buttons

export default function DisputeCard({ msg, onApprove, onReject }) {
  const { dispute_found, reversal_recommended, confidence,
          original_tx_id, duplicate_tx_id } = msg;

  if (!dispute_found) return null;

  const pct = Math.round((confidence || 0) * 100);

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
          <p style={s.rec}>Reversal recommended. Approve to reverse the duplicate charge.</p>
          <div style={s.btns}>
            <button style={s.approve}
              onClick={() => onApprove(original_tx_id, duplicate_tx_id)}>
              ✓ Approve reversal
            </button>
            <button style={s.reject}
              onClick={() => onReject(duplicate_tx_id, original_tx_id)}>
              ✗ Reject
            </button>
          </div>
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
  btns:    { display: "flex", gap: 8 },
  approve: { padding: "7px 16px", borderRadius: 8, border: "none",
             background: "#16A34A", color: "#fff", fontWeight: 600,
             fontSize: 13, cursor: "pointer" },
  reject:  { padding: "7px 16px", borderRadius: 8,
             border: "1px solid #E2E8F0", background: "#fff",
             color: "#64748B", fontWeight: 600, fontSize: 13, cursor: "pointer" },
};
