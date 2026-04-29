// ResultsTable.jsx
import { useState } from "react";

const STATUS_COLORS = {
  APPROVED: { bg: "#DCFCE7", color: "#166534" },
  DECLINED: { bg: "#FEE2E2", color: "#991B1B" },
  REVERSED: { bg: "#FEF3C7", color: "#92400E" },
  PENDING:  { bg: "#DBEAFE", color: "#1E40AF" },
};

const PAGE_SIZE = 20;

export default function ResultsTable({ rows, rowCount }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [page,    setPage]    = useState(0);

  if (!rows || rows.length === 0) return null;

  const columns = Object.keys(rows[0]);

  const sorted = [...rows].sort((a, b) => {
    if (!sortCol) return 0;
    const av = a[sortCol], bv = b[sortCol];
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const paged      = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
    setPage(0);
  }

  function fmt(val, col) {
    if (val == null) return "—";
    if (typeof val === "string" && val.includes("T") && val.includes(":"))
      return val.replace("T", " ").slice(0, 19);
    if (typeof val === "number") return val.toLocaleString();
    if (typeof val === "boolean") return val ? "✓" : "✗";
    return String(val);
  }

  function fmtHeader(col) {
    return col.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function cellStyle(col, val) {
    if (col === "status" && STATUS_COLORS[val]) {
      return {
        ...STATUS_COLORS[val],
        padding: "2px 8px", borderRadius: 10,
        fontSize: 11, fontWeight: 600, whiteSpace: "nowrap"
      };
    }
    if (col === "amount") {
      return { color: parseFloat(val) < 0 ? "#DC2626" : "#0F172A",
               fontVariantNumeric: "tabular-nums", fontWeight: 500 };
    }
    if (col === "loyalty_points_credited") {
      return { color: val ? "#16A34A" : "#DC2626", fontWeight: 600 };
    }
    return {};
  }

  return (
    <div style={s.wrapper}>
      <div style={s.meta}>
        {rowCount.toLocaleString()} result{rowCount !== 1 ? "s" : ""}
        {rowCount > rows.length && ` (showing first ${rows.length})`}
      </div>

      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col} style={s.th} onClick={() => handleSort(col)}>
                  {fmtHeader(col)}
                  <span style={s.sortIcon}>
                    {sortCol === col ? (sortDir === "asc" ? " ↑" : " ↓") : " ↕"}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => (
              <tr key={i} style={i % 2 === 0 ? s.trEven : s.trOdd}>
                {columns.map(col => (
                  <td key={col} style={s.td}>
                    <span style={cellStyle(col, row[col])}>
                      {fmt(row[col], col)}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div style={s.pagination}>
          <button style={s.pgBtn}
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}>← Prev</button>
          <span style={s.pgInfo}>Page {page + 1} of {totalPages}</span>
          <button style={s.pgBtn}
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}>Next →</button>
        </div>
      )}
    </div>
  );
}

const s = {
  wrapper:   { marginTop: 8, fontSize: 13 },
  meta:      { color: "#94A3B8", fontSize: 12, marginBottom: 6 },
  tableWrap: { overflowX: "auto", borderRadius: 8, border: "1px solid #E2E8F0" },
  table:     { width: "100%", borderCollapse: "collapse", fontSize: 12 },
  th: {
    background: "#F8FAFC", padding: "8px 12px",
    textAlign: "left", fontWeight: 600, color: "#475569",
    cursor: "pointer", whiteSpace: "nowrap",
    borderBottom: "1px solid #E2E8F0", userSelect: "none", fontSize: 11
  },
  sortIcon:  { color: "#CBD5E1" },
  td:        { padding: "7px 12px", color: "#334155", whiteSpace: "nowrap", borderBottom: "1px solid #F1F5F9" },
  trEven:    { background: "#FFFFFF" },
  trOdd:     { background: "#F8FAFC" },
  pagination:{ display: "flex", alignItems: "center", gap: 12, marginTop: 8, justifyContent: "flex-end" },
  pgBtn:     { padding: "4px 12px", border: "1px solid #E2E8F0", borderRadius: 6, background: "#fff", cursor: "pointer", fontSize: 12 },
  pgInfo:    { color: "#94A3B8", fontSize: 12 },
};
