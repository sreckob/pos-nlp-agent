// RoleSelector.jsx
// Opening screen — user identifies their role before chat starts

const ROLES = [
  {
    id:       "CARDHOLDER",
    icon:     "💳",
    title:    "Cardholder",
    subtitle: "Check your personal transactions",
    color:    "#2563EB",
    bg:       "#EFF6FF",
    border:   "#BFDBFE",
  },
  {
    id:       "MERCHANT",
    icon:     "🏪",
    title:    "Merchant",
    subtitle: "View terminal & sales data",
    color:    "#0D9488",
    bg:       "#F0FDFA",
    border:   "#99F6E4",
  },
  {
    id:       "DISPUTE",
    icon:     "⚠️",
    title:    "Dispute",
    subtitle: "Report a double charge or error",
    color:    "#DC2626",
    bg:       "#FEF2F2",
    border:   "#FECACA",
  },
  {
    id:       "LOYALTY",
    icon:     "⭐",
    title:    "Loyalty",
    subtitle: "Check or recover your points",
    color:    "#D97706",
    bg:       "#FFFBEB",
    border:   "#FDE68A",
  },
];

export default function RoleSelector({ onSelect }) {
  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <div style={styles.logo}>POS</div>
        <h1 style={styles.title}>Transaction Query Agent</h1>
        <p style={styles.subtitle}>
          Natural language queries for POS payment data
        </p>
      </div>

      <p style={styles.prompt}>Who are you?</p>

      <div style={styles.grid}>
        {ROLES.map((role) => (
          <button
            key={role.id}
            style={{ ...styles.card, borderColor: role.border, background: role.bg }}
            onClick={() => onSelect(role.id)}
          >
            <span style={styles.icon}>{role.icon}</span>
            <span style={{ ...styles.cardTitle, color: role.color }}>{role.title}</span>
            <span style={styles.cardSub}>{role.subtitle}</span>
          </button>
        ))}
      </div>

      <p style={styles.footer}>
        Powered by Claude Sonnet · LangGraph · PostgreSQL
      </p>
    </div>
  );
}

const styles = {
  wrapper: {
    display:        "flex",
    flexDirection:  "column",
    alignItems:     "center",
    justifyContent: "center",
    minHeight:      "100vh",
    padding:        "40px 24px",
    background:     "#F8FAFC",
    fontFamily:     "'DM Sans', -apple-system, sans-serif",
  },
  header: {
    textAlign:    "center",
    marginBottom: 40,
  },
  logo: {
    display:        "inline-flex",
    alignItems:     "center",
    justifyContent: "center",
    width:          56,
    height:         56,
    borderRadius:   14,
    background:     "#1E40AF",
    color:          "#fff",
    fontWeight:     800,
    fontSize:       18,
    letterSpacing:  1,
    marginBottom:   16,
  },
  title: {
    fontSize:     28,
    fontWeight:   700,
    color:        "#0F172A",
    margin:       0,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 15,
    color:    "#64748B",
    margin:   0,
  },
  prompt: {
    fontSize:     13,
    fontWeight:   600,
    color:        "#94A3B8",
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom:  16,
  },
  grid: {
    display:             "grid",
    gridTemplateColumns: "repeat(2, 1fr)",
    gap:                 16,
    width:               "100%",
    maxWidth:            560,
  },
  card: {
    display:        "flex",
    flexDirection:  "column",
    alignItems:     "flex-start",
    padding:        "20px 22px",
    borderRadius:   14,
    border:         "1.5px solid",
    cursor:         "pointer",
    textAlign:      "left",
    transition:     "transform 0.15s, box-shadow 0.15s",
    outline:        "none",
  },
  icon: {
    fontSize:     28,
    marginBottom: 10,
  },
  cardTitle: {
    fontSize:     16,
    fontWeight:   700,
    marginBottom: 4,
  },
  cardSub: {
    fontSize: 13,
    color:    "#64748B",
  },
  footer: {
    marginTop: 48,
    fontSize:  12,
    color:     "#CBD5E1",
  },
};
