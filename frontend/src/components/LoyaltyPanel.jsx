// LoyaltyPanel.jsx
// Shown on loyalty path — displays missing points.
// Customer clicks "Submit for review" → enqueues to ops console.

import { useState } from "react";

export default function LoyaltyPanel({ msg, onSubmit }) {
  const { pan_enrolled, missing_points, credit_recommended, pan_masked } = msg;
  const [submitted, setSubmitted] = useState(false);

  if (!pan_enrolled && !missing_points) return null;

  function handleClick() {
    setSubmitted(true);
    onSubmit(pan_masked, missing_points, msg);
  }

  return (
    <div style={s.card}>
      <div style={s.header}>
        <span style={s.icon}>⭐</span>
        <span style={s.title}>Loyalty points</span>
      </div>

      {!pan_enrolled ? (
        <p style={s.text}>This card is not enrolled in the loyalty program.</p>
      ) : (
        <>
          {missing_points > 0 ? (
            <>
              <div style={s.pointsRow}>
                <span style={s.label}>Missing points</span>
                <span style={s.points}>{missing_points.toLocaleString()}</span>
              </div>
              {credit_recommended && !submitted && (
                <div style={s.actions}>
                  <p style={s.rec}>
                    Click Submit for review and operations will credit {missing_points} points.
                  </p>
                  <button style={s.btn} onClick={handleClick}>
                    Submit for review
                  </button>
                </div>
              )}
              {submitted && (
                <div style={s.submitted}>
                  ✓ Submitted to operations. You will be notified when the review completes.
                </div>
              )}
            </>
          ) : (
            <p style={s.text}>All points have been correctly credited.</p>
          )}
        </>
      )}
    </div>
  );
}

const s = {
  card:      { background: "#FFFBEB", border: "1px solid #FDE68A",
               borderRadius: 10, padding: "14px 16px", marginTop: 8 },
  header:    { display: "flex", alignItems: "center", gap: 8, marginBottom: 10 },
  icon:      { fontSize: 16 },
  title:     { fontWeight: 600, fontSize: 13, color: "#92400E" },
  pointsRow: { display: "flex", justifyContent: "space-between",
               alignItems: "center", marginBottom: 10 },
  label:     { fontSize: 12, color: "#92400E", fontWeight: 600 },
  points:    { fontSize: 22, fontWeight: 800, color: "#D97706" },
  text:      { fontSize: 12, color: "#92400E", margin: 0 },
  rec:       { fontSize: 12, color: "#92400E", margin: "0 0 10px 0" },
  actions:   {},
  btn:       { padding: "8px 18px", borderRadius: 8, border: "none",
               background: "#D97706", color: "#fff", fontWeight: 600,
               fontSize: 13, cursor: "pointer" },
  submitted: { fontSize: 12, color: "#15803D", background: "#DCFCE7",
               padding: "8px 12px", borderRadius: 8, marginTop: 6 },
};
