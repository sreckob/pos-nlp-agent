// ApprovalDetail.jsx — shows one pending approval + agent recommendation
// + Approve / Reject buttons that hit /ops/decide.

import { useEffect, useState } from "react";
import { fetchPendingDetail, decideApproval } from "../api";

export default function ApprovalDetail({ approvalId, onDecided }) {
  const [detail,   setDetail]   = useState(null);
  const [loading,  setLoading]  = useState(true);
  const [deciding, setDeciding] = useState(false);
  const [result,   setResult]   = useState(null);

  useEffect(() => {
    let alive = true;
    setResult(null);
    setDetail(null);
    if (!approvalId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchPendingDetail(approvalId)
      .then(d => { if (alive) { setDetail(d); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [approvalId]);

  async function handleDecide(decision) {
    setDeciding(true);
    try {
      const r = await decideApproval(approvalId, decision);
      setResult(r);
      onDecided?.(r);
    } finally {
      setDeciding(false);
    }
  }

  if (!approvalId) {
    return <div style={styles.empty}>Select a pending item to review.</div>;
  }
  if (loading) {
    return <div style={styles.empty}>Loading approval detail…</div>;
  }
  if (!detail) {
    return <div style={styles.empty}>Could not load approval.</div>;
  }

  const rec = detail.agent_recommendation || {};
  const isDispute = detail.type === "DISPUTE";
  const payload = detail.payload || {};
  const recColor = rec.decision === "APPROVE" ? "#16A34A"
                  : rec.decision === "REJECT" ? "#DC2626"
                  : "#64748B";

  return (
    <div style={styles.wrap}>
      <div style={styles.header}>
        <span style={{ ...styles.badge, background: isDispute ? "#FEE2E2" : "#FEF3C7",
                       color: isDispute ? "#991B1B" : "#92400E" }}>
          {isDispute ? "⚠ Dispute reversal" : "★ Loyalty credit"}
        </span>
        <span style={styles.id}>{detail.id}</span>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>Customer submission</div>
        <pre style={styles.pre}>{JSON.stringify(payload, null, 2)}</pre>
        <div style={styles.meta}>
          Session: {detail.customer_session_id?.slice(0, 8)}…
          {" · "}Submitted: {new Date(detail.created_at).toLocaleString()}
        </div>
      </div>

      <div style={styles.section}>
        <div style={styles.sectionTitle}>Approver agent recommendation</div>
        <div style={{ ...styles.recBox, borderColor: recColor }}>
          <div style={{ ...styles.recHeader, color: recColor }}>
            {rec.decision || "—"}
            {rec.confidence != null && (
              <span style={styles.conf}>
                {Math.round(rec.confidence * 100)}% confidence
              </span>
            )}
          </div>
          {rec.audit_summary && (
            <div style={styles.summary}>{rec.audit_summary}</div>
          )}
          {rec.blocking_reason && (
            <div style={styles.block}>Blocking: {rec.blocking_reason}</div>
          )}
        </div>
      </div>

      {result ? (
        <div style={styles.resultBox}>
          <div style={styles.resultTitle}>
            Decision: {result.decision || result.message}
          </div>
          {result.audit_summary && (
            <div style={styles.summary}>{result.audit_summary}</div>
          )}
          {result.write_result?.message && (
            <div style={styles.summary}>{result.write_result.message}</div>
          )}
          <div style={styles.meta}>
            Customer notified: {result.customer_notified ? "yes" : "no (offline)"}
          </div>
        </div>
      ) : (
        <div style={styles.actions}>
          <button
            style={{ ...styles.btn, background: "#DC2626" }}
            disabled={deciding}
            onClick={() => handleDecide("REJECT")}
          >
            Reject
          </button>
          <button
            style={{ ...styles.btn, background: "#16A34A" }}
            disabled={deciding}
            onClick={() => handleDecide("APPROVE")}
          >
            {deciding ? "Processing…" : "Approve"}
          </button>
        </div>
      )}
    </div>
  );
}

const styles = {
  wrap:    { padding: 16, height: "100%", overflowY: "auto", background: "#F8FAFC" },
  empty:   { padding: 40, color: "#94A3B8", textAlign: "center", fontSize: 13 },
  header:  { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 },
  badge:   { padding: "4px 10px", borderRadius: 12, fontSize: 12, fontWeight: 600 },
  id:      { fontFamily: "monospace", fontSize: 11, color: "#94A3B8" },
  section: { background: "#fff", borderRadius: 10, padding: 14, marginBottom: 12,
             border: "1px solid #E2E8F0" },
  sectionTitle: { fontSize: 11, fontWeight: 600, textTransform: "uppercase",
                  letterSpacing: 0.4, color: "#64748B", marginBottom: 8 },
  pre:     { margin: 0, fontSize: 11, color: "#334155", whiteSpace: "pre-wrap",
             wordBreak: "break-all", background: "#F8FAFC", padding: 10, borderRadius: 6 },
  meta:    { fontSize: 11, color: "#94A3B8", marginTop: 8 },
  recBox:  { padding: 12, borderRadius: 8, border: "2px solid", background: "#fff" },
  recHeader: { fontSize: 16, fontWeight: 700, display: "flex", justifyContent: "space-between" },
  conf:    { fontSize: 11, color: "#64748B", fontWeight: 500 },
  summary: { fontSize: 13, color: "#334155", marginTop: 6, lineHeight: 1.5 },
  block:   { fontSize: 12, color: "#DC2626", marginTop: 6 },
  actions: { display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 16 },
  btn:     { padding: "10px 22px", borderRadius: 10, border: "none",
             color: "#fff", fontWeight: 600, fontSize: 14, cursor: "pointer" },
  resultBox: { background: "#ECFDF5", border: "1px solid #16A34A",
               borderRadius: 10, padding: 14, marginTop: 12 },
  resultTitle: { fontWeight: 700, color: "#14532D", marginBottom: 4 },
};
