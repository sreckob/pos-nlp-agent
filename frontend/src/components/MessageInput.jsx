// MessageInput — owns its own text state so typing doesn't re-render
// the parent's message list. Parent can imperatively focus or set the
// text via ref (e.g., when an example chip is clicked).

import {
  useState, useRef, forwardRef, useImperativeHandle,
} from "react";

const MessageInput = forwardRef(function MessageInput(
  { onSend, placeholder, accentColor, disabled },
  ref,
) {
  const [text, setText] = useState("");
  const taRef = useRef(null);

  useImperativeHandle(ref, () => ({
    focus: () => taRef.current?.focus(),
    setText: (value) => {
      setText(value);
      setTimeout(() => taRef.current?.focus(), 0);
    },
    clear: () => setText(""),
  }));

  function submit() {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
    taRef.current?.focus();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div style={s.row}>
      <textarea
        ref={taRef}
        style={s.textarea}
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={1}
        disabled={disabled}
      />
      <button
        style={{
          ...s.btn,
          background: accentColor,
          opacity: (!text.trim() || disabled) ? 0.5 : 1,
        }}
        onClick={submit}
        disabled={!text.trim() || disabled}
      >
        Send
      </button>
    </div>
  );
});

export default MessageInput;

const s = {
  row: { display: "flex", gap: 8, marginTop: 8 },
  textarea: {
    flex: 1, padding: "10px 14px", borderRadius: 12,
    border: "1px solid #E2E8F0", fontSize: 14, resize: "none",
    fontFamily: "inherit", outline: "none", lineHeight: 1.5,
    background: "#F8FAFC",
  },
  btn: {
    padding: "10px 20px", borderRadius: 12, border: "none",
    color: "#fff", fontWeight: 600, fontSize: 14, cursor: "pointer",
  },
};
