"""
Session Store
=============
In-memory session management.
Each session holds:
  - history     : list of {role, content} messages for the LLM
  - last_sql    : the last SQL query that was executed
  - last_rows   : the last result set returned
  - role        : classified user role (CARDHOLDER/MERCHANT/DISPUTE/LOYALTY)
  - language    : detected language (sr/en)
  - created_at  : session creation timestamp
  - turn_count  : number of turns in this session

For production, replace with Redis using the same interface.
"""

from datetime import datetime
from typing import Any, Dict, Optional


class SessionStore:

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "history":     [],
                "last_sql":    None,
                "last_rows":   [],
                "role":        None,      # set by router on first turn
                "language":    "en",      # default, updated by router
                "created_at":  datetime.utcnow().isoformat(),
                "turn_count":  0
            }
        return self._sessions[session_id]

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)

    def set_role(self, session_id: str, role: str, language: str = "en"):
        """Set the user role after router classification."""
        session = self.get_or_create(session_id)
        session["role"]     = role
        session["language"] = language

    def update(
        self,
        session_id:        str,
        user_message:      str,
        assistant_message: str,
        sql:               Optional[str] = None,
        rows:              Optional[list] = None,
        role:              Optional[str] = None,
        language:          Optional[str] = None,
    ):
        session = self.get_or_create(session_id)
        session["history"].append({"role": "user",      "content": user_message})
        session["history"].append({"role": "assistant", "content": assistant_message})
        if sql:
            session["last_sql"] = sql
        if rows is not None:
            session["last_rows"] = rows
        if role:
            session["role"] = role
        if language:
            session["language"] = language
        session["turn_count"] += 1

        # Keep history bounded — last 20 messages (10 turns)
        if len(session["history"]) > 20:
            session["history"] = session["history"][-20:]

    def clear(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]

    def active_sessions(self) -> int:
        return len(self._sessions)
