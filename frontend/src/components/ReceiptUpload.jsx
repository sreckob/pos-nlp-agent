// ReceiptUpload.jsx
// File upload component for dispute path
// Converts image to base64 and sends as part of the message

import { useRef, useState } from "react";

export default function ReceiptUpload({ onUpload }) {
  const inputRef   = useRef(null);
  const [preview, setPreview] = useState(null);
  const [name,    setName]    = useState(null);

  function handleFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    setName(file.name);

    const reader = new FileReader();
    reader.onload = (ev) => {
      const base64 = ev.target.result;
      setPreview(base64);
      onUpload({ base64, filename: file.name, type: file.type });
    };
    reader.readAsDataURL(file);
  }

  function clear() {
    setPreview(null);
    setName(null);
    onUpload(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div style={s.wrapper}>
      {!preview ? (
        <button style={s.uploadBtn} onClick={() => inputRef.current?.click()}>
          📎 Attach receipt
        </button>
      ) : (
        <div style={s.preview}>
          <img src={preview} alt="receipt" style={s.img} />
          <div style={s.previewInfo}>
            <span style={s.filename}>{name}</span>
            <button style={s.clearBtn} onClick={clear}>✕ Remove</button>
          </div>
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/*,.pdf"
        style={{ display: "none" }}
        onChange={handleFile}
      />
    </div>
  );
}

const s = {
  wrapper:     { marginTop: 6 },
  uploadBtn:   { padding: "6px 14px", borderRadius: 8,
                 border: "1px dashed #E2E8F0", background: "#F8FAFC",
                 color: "#64748B", fontSize: 13, cursor: "pointer" },
  preview:     { display: "flex", alignItems: "center", gap: 10,
                 background: "#F8FAFC", borderRadius: 8,
                 border: "1px solid #E2E8F0", padding: "8px 12px" },
  img:         { width: 48, height: 48, objectFit: "cover",
                 borderRadius: 6, border: "1px solid #E2E8F0" },
  previewInfo: { flex: 1 },
  filename:    { fontSize: 12, color: "#334155", display: "block", marginBottom: 4 },
  clearBtn:    { background: "none", border: "none", color: "#94A3B8",
                 fontSize: 11, cursor: "pointer", padding: 0 },
};
