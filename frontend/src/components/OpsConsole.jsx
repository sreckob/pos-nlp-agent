// OpsConsole.jsx — operations approver dashboard.
// Two columns: queue list (left) + approval detail (right).

import { useState } from "react";
import OpsQueue       from "./OpsQueue";
import ApprovalDetail from "./ApprovalDetail";

export default function OpsConsole() {
  const [selectedId, setSelectedId] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  function handleDecided() {
    setRefreshKey(k => k + 1);
    setSelectedId(null);
  }

  return (
    <div style={styles.wrap}>
      <div style={styles.header}>
        <span style={styles.title}>Ops Approver Console</span>
        <span style={styles.sub}>Reviews customer-submitted disputes and loyalty credits</span>
      </div>
      <div style={styles.body}>
        <div style={styles.left}>
          <OpsQueue
            selectedId={selectedId}
            onSelect={setSelectedId}
            refreshKey={refreshKey}
          />
        </div>
        <div style={styles.right}>
          <ApprovalDetail
            approvalId={selectedId}
            onDecided={handleDecided}
          />
        </div>
      </div>
    </div>
  );
}

const styles = {
  wrap:    { display: "flex", flexDirection: "column", height: "100%",
             background: "#fff", borderLeft: "1px solid #E2E8F0" },
  header:  { padding: "12px 18px", borderBottom: "1px solid #E2E8F0",
             background: "#0F172A", color: "#fff" },
  title:   { fontSize: 14, fontWeight: 700, display: "block" },
  sub:     { fontSize: 11, color: "#94A3B8" },
  body:    { flex: 1, display: "flex", overflow: "hidden" },
  left:    { width: 280, flexShrink: 0 },
  right:   { flex: 1, overflow: "hidden" },
};
