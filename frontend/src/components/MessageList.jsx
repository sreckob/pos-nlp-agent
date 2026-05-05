// MessageList — memoized message render loop. Re-renders only when
// messages, isTyping, or the action handlers actually change reference.
// Parent should pass useCallback-wrapped handlers for max benefit.

import { memo } from "react";
import Message from "./Message";

function MessageList({ messages, isTyping, onSubmitDispute, onSubmitLoyalty }) {
  return (
    <>
      {messages.map(msg => (
        <Message
          key={msg.id}
          msg={msg}
          onSubmitDispute={onSubmitDispute}
          onSubmitLoyalty={onSubmitLoyalty}
        />
      ))}
      {isTyping && (
        <div style={s.typing}>
          <span style={s.dot} />
          <span style={s.dot} />
          <span style={s.dot} />
        </div>
      )}
    </>
  );
}

export default memo(MessageList);

const s = {
  typing: {
    display: "flex", gap: 4, padding: "10px 14px",
    background: "#F1F5F9", borderRadius: "18px 18px 18px 4px",
    width: "fit-content", marginBottom: 16,
  },
  dot: {
    width: 7, height: 7, borderRadius: "50%", background: "#94A3B8",
    display: "inline-block", animation: "pulse 1.2s ease-in-out infinite",
  },
};
