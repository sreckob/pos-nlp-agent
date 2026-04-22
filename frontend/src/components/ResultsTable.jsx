// ResultsTable.jsx
// Renders query results as a sortable table

import { useState } from "react";

export default function ResultsTable({ rows, rowCount }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [page, setPage]       = useState(0);
  const PAGE_SIZE = 20;

  if (!rows || rows.length === 0) return null;

  const columns = Object.keys(rows[0]);

  // Sorting
  const sorted = [...rows].sort((a, b) => {
    if (!sortCol) return 0;
    const av = a[sortCol], bv = b[sortCol];
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return sortDir === "asc" ? cmp : -cmp;
  });

  // Pagination
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleSort(col) {
    if (sortCol === col) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
    setPage(0);
  }

  function formatValue(val) {
    if (val == null) return "—";
    if (typeof val === "string" && val.includes("T") && val.includes(":")) {
      // looks like ISO timestamp
      return val.replace("T", " ").slice(0, 19);
    }
    if (typeof val === "number") return val.toLocaleString();
    return String(val);
  }

  function formatHeader(col) {
    return col.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  return (
    <div style={styles.wrapper}>
      <div style={styles.meta}>
        {rowCount} result{rowCount !== 1 ? "s" : ""}
        {rowCount > rows.length && ` (showing first ${rows.length})`}
      </div>

      <div style={styles.tableWrapper}>
        <table style={styles.table}>
          <thead>
            <tr>
              {columns.map(col => (
                <th
                  key={col}
                  style={styles.th}
                  onClick={() => handleSort(col)}
                >
                  {formatHeader(col)}
                  {sortCol === col ? (sortDir === "asc" ? " ↑" : " ↓") : " ↕"}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => (
              <tr key={i} style={i % 2 === 0 ? styles.trEven : styles.trOdd}>
                {columns.map(col => (
                  <td key={col} style={styles.td}>
                    <span style={getCellStyle(col, row[col])}>
                      {formatValue(row[col])}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div style={styles.pagination}>
          <button
            style={styles.pageBtn}
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
          >
            ← Prev
          </button>
          <span style={styles.pageInfo}>
            Page {page + 1} of {totalPages}
          </span>
          <button
            style={styles.pageBtn}
            onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

function getCellStyle(col, val) {
  if (col === "status") {
    const colors = {
      APPROVED: { background: "#d1fae5", color: "#065f46" },
      DECLINED: { background: "#fee2e2", color: "#991b1b" },
      REVERSED: { background: "#fef3c7", color: "#92400e" },
      PENDING:  { background: "#e0f2fe", color: "#0c4a6e" },
    };
    return {
      ...colors[val],
      padding: "2px 8px",
      borderRadius: 12,
      fontSize: 12,
      fontWeight: 600,
      whiteSpace: "nowrap"
    };
  }
  if (col === "amount") {
    const num = parseFloat(val);
    return { color: num < 0 ? "#dc2626" : "#111", fontVariantNumeric: "tabular-nums" };
  }
  return {};
}

const styles = {
  wrapper: {
    marginTop: 8,
    fontSize: 13
  },
  meta: {
    color: "#6b7280",
    fontSize: 12,
    marginBottom: 6
  },
  tableWrapper: {
    overflowX: "auto",
    borderRadius: 8,
    border: "1px solid #e5e7eb"
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13
  },
  th: {
    background: "#f9fafb",
    padding: "8px 12px",
    textAlign: "left",
    fontWeight: 600,
    color: "#374151",
    cursor: "pointer",
    whiteSpace: "nowrap",
    borderBottom: "1px solid #e5e7eb",
    userSelect: "none"
  },
  td: {
    padding: "7px 12px",
    color: "#374151",
    whiteSpace: "nowrap",
    borderBottom: "1px solid #f3f4f6"
  },
  trEven: { background: "#ffffff" },
  trOdd:  { background: "#f9fafb" },
  pagination: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginTop: 8,
    justifyContent: "flex-end"
  },
  pageBtn: {
    padding: "4px 12px",
    border: "1px solid #d1d5db",
    borderRadius: 6,
    background: "#fff",
    cursor: "pointer",
    fontSize: 13
  },
  pageInfo: {
    color: "#6b7280",
    fontSize: 13
  }
};
