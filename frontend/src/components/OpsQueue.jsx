// OpsQueue.jsx — list of pending approvals, polls every 4s

import { useEffect, useState } from "react";
import { fetchOpsQueue } from "../api";

export default function OpsQueue({ selectedId, onSelect, refreshKey }) {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const data = await fetchOpsQueue();
        if (!alive) return;
        setPending(data.pending || []);
        setLoading(false);
      } catch {
        setLoading(false);
      }
    }
    load();
    const t = setInterval(load, 4000);
    return () => { alive = false; clearInterval(t); };
  }, [refreshKey]);

  return (
    <div style={styles.wrap}>
      <div style={styles.header}>
        <span style={styles.title}>Pending queue</span>
        <span style={styles.count}>{pending.length}</span>
      </div>
      <div style={styles.list}>
        {loading && <div style={styles.empty}>Loading…</div>}
        {!loading && pending.length === 0 && (
          <div style={styles.empty}>No pending approvals.</div>
        )}
        {pending.map(item => (
          <button
            key={item.id}
            style={{
              ...styles.item,
              ...(selectedId === item.id ? styles.itemSelected : {}),
              borderLeftColor: item.type === "DISPUTE" ? "#DC2626" : "#D97706",
            }}
            onClick={() => onSelect(item.id)}
          >
            <div style={styles.row1}>
              <span style={styles.type}>
                {item.type === "DISPUTE" ? "⚠ Dispute" : "★ Loyalty"}
              </span>
              <span style={styles.id}>{item.id.slice(0, 8)}</span>
            </div>
            <div style={styles.row2}>
              {summarize(item)}
            </div>
            <div style={styles.row3}>
              {new Date(item.created_at).toLocaleTimeString()}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function summarize(item) {
  const p = item.payload || {};
  if (item.type === "DISPUTE") {
    return `${p.merchant_name || "?"} · ${p.amount ?? "?"} RSD · ${maskTail(p.pan_masked)}`;
  }
  return `${maskTail(p.pan_masked)} · ${p.points_to_add} points`;
}

function maskTail(pan) {
  if (!pan) return "????";
  return "…" + pan.slice(-4);
}

const styles = {
  wrap: {
    display: "flex", flexDirection: "column", height: "100%",
    background: "#fff", borderRight: "1px solid #E2E8F0",
  },
  header: {
    padding: "12px 16px", borderBottom: "1px solid #E2E8F0",
    display: "flex", justifyContent: "space-between", alignItems: "center",
  },
  title: { fontSize: 13, fontWeight: 600, color: "#334155" },
  count: {
    background: "#0F172A", color: "#fff", fontSize: 11, fontWeight: 600,
    padding: "2px 8px", borderRadius: 10,
  },
  list:  { flex: 1, overflowY: "auto" },
  empty: { padding: 20, color: "#94A3B8", fontSize: 13, textAlign: "center" },
  item: {
    width: "100%", textAlign: "left", padding: "10px 14px",
    borderTop: "1px solid #F1F5F9", borderLeft: "3px solid",
    borderRight: "none", borderBottom: "none",
    background: "#fff", cursor: "pointer", fontFamily: "inherit",
  },
  itemSelected: { background: "#F1F5F9" },
  row1: { display: "flex", justifyContent: "space-between", marginBottom: 4 },
  type: { fontSize: 12, fontWeight: 600, color: "#334155" },
  id:   { fontSize: 11, color: "#94A3B8", fontFamily: "monospace" },
  row2: { fontSize: 12, color: "#475569", marginBottom: 2 },
  row3: { fontSize: 10, color: "#94A3B8" },
};
