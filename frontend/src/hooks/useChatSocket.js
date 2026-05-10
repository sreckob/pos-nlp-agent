// useChatSocket — owns the WebSocket connection, the chat messages
// array, role state, and the four inbound frame handlers. Also handles
// reconnection with exponential backoff.

import { useState, useEffect, useRef, useCallback } from "react";
import { createWebSocket, sendMessage as sendWS, getNewSessionId } from "../api";

const RECONNECT_MAX_DELAY_MS = 15000;

export function useChatSocket() {
  const [messages,  setMessages]  = useState([]);
  const [isTyping,  setIsTyping]  = useState(false);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [role,      setRole]      = useState(null);

  const wsRef            = useRef(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer   = useRef(null);
  const sessionIdRef     = useRef(null);
  // Track latest role without putting it in handler deps (would re-create
  // the WS on every role change).
  const roleRef          = useRef(null);
  useEffect(() => { roleRef.current = role; }, [role]);

  // ── Inbound frame router ─────────────────────────────────────
  const handleMessage = useCallback((data) => {
    if (data.type === "typing") {
      setIsTyping(true);
      return;
    }
    if (data.type === "response") {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        id:                   Date.now(),
        role:                 "assistant",
        agentRole:            data.role,
        content:              data.message,
        sql:                  data.sql,
        rows:                 data.rows || [],
        rowCount:             data.row_count || 0,
        timestamp:            new Date().toLocaleTimeString(),
        suggest_switch:       data.suggest_switch,
        pending_role:         data.pending_role,
        dispute_found:        data.dispute_found,
        reversal_recommended: data.reversal_recommended,
        original_tx_id:       data.original_tx_id,
        duplicate_tx_id:      data.duplicate_tx_id,
        confidence:           data.confidence,
        pan_enrolled:         data.pan_enrolled,
        missing_points:       data.missing_points,
        credit_recommended:   data.credit_recommended,
        pan_masked:           data.pan_masked,
        language:             data.language,
        has_export:           data.has_export,
      }]);
      // Confirmed channel switch → update role badge.
      if (data.role && !data.suggest_switch && data.role !== roleRef.current) {
        setRole(data.role);
      }
      // Three-strike force reset → return to role selector.
      if (data.force_reset) {
        setTimeout(() => {
          setRole(null);
          setMessages([]);
        }, 2500);
      }
      return;
    }
    if (data.type === "error") {
      setIsTyping(false);
      setMessages(prev => [...prev, {
        id:        Date.now(),
        role:      "assistant",
        content:   data.message,
        timestamp: new Date().toLocaleTimeString(),
      }]);
      return;
    }
    if (data.type === "approval_decided") {
      const sr      = data.language === "sr";
      const ok      = data.write_result?.message;
      const audit   = data.audit_summary || "";
      const body    = data.decision === "APPROVED"
        ? (sr ? "✓ Vaš zahtev je odobren od strane operacija. "
              : "✓ Your request has been approved by operations. ") + (ok || audit)
        : (sr ? "✗ Vaš zahtev je odbijen od strane operacija. "
              : "✗ Your request was rejected by operations. ") + audit;
      setMessages(prev => [...prev, {
        id:        Date.now(),
        role:      "assistant",
        agentRole: data.approval_type,
        content:   body,
        timestamp: new Date().toLocaleTimeString(),
      }]);
    }
  }, []);

  // ── (Re)connect with backoff ─────────────────────────────────
  const connect = useCallback((sid) => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);

    // Null out the old socket's onclose BEFORE closing it so we don't
    // trigger an extra reconnect cycle from the socket being replaced.
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    const onOpen = () => {
      setConnected(true);
      reconnectAttempt.current = 0;
    };

    const onClose = () => {
      setConnected(false);
      const delay = Math.min(
        1000 * (2 ** reconnectAttempt.current),
        RECONNECT_MAX_DELAY_MS
      );
      reconnectAttempt.current += 1;
      const targetSid = sessionIdRef.current || sid;
      reconnectTimer.current = setTimeout(() => connect(targetSid), delay);
    };

    wsRef.current = createWebSocket(
      sid,
      handleMessage,
      onOpen,
      () => {},      // onError — onClose always follows, handled there
      onClose,
    );
  }, [handleMessage]);

  // ── Initial connection ───────────────────────────────────────
  useEffect(() => {
    let alive = true;
    getNewSessionId().then(sid => {
      if (!alive) return;
      sessionIdRef.current = sid;
      setSessionId(sid);
      connect(sid);
    });
    return () => {
      alive = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  // ── Public actions ───────────────────────────────────────────
  const sendChat = useCallback((text, imageData = null) => {
    sendWS(wsRef.current, text, imageData);
  }, []);

  const addMessage = useCallback((msg) => {
    setMessages(prev => [...prev, {
      id:        msg.id ?? Date.now(),
      timestamp: msg.timestamp ?? new Date().toLocaleTimeString(),
      ...msg,
    }]);
  }, []);

  const newSession = useCallback(async () => {
    const sid = await getNewSessionId();
    sessionIdRef.current = sid;
    setSessionId(sid);
    setMessages([]);
    setRole(null);
    connect(sid);
  }, [connect]);

  return {
    messages, isTyping, connected, sessionId, role,
    setRole, sendChat, addMessage, newSession,
  };
}
