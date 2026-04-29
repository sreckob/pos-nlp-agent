"""
Session Store v2.2
==================
In-memory session management.
Tracks mismatch_count for three-strike channel enforcement.
"""

from datetime import datetime
from typing import Any, Dict, Optional


class SessionStore:

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def get_or_create(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "history":        [],
                "last_sql":       None,
                "last_rows":      [],
                "role":           None,
                "pending_role":   None,   # suggested switch target
                "mismatch_count": 0,      # consecutive mismatches on same channel
                "language":       "en",
                "created_at":     datetime.utcnow().isoformat(),
                "turn_count":     0
            }
        return self._sessions[session_id]

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)

    def set_role(self, session_id: str, role: str, language: str = "en"):
        """Set role and reset mismatch counter."""
        session = self.get_or_create(session_id)
        session["role"]           = role
        session["language"]       = language
        session["pending_role"]   = None
        session["mismatch_count"] = 0   # reset on role change

    def increment_mismatch(self, session_id: str) -> int:
        """Increment mismatch counter and return new count."""
        session = self.get_or_create(session_id)
        session["mismatch_count"] += 1
        return session["mismatch_count"]

    def reset_mismatch(self, session_id: str):
        """Reset mismatch counter when user matches their channel."""
        session = self.get_or_create(session_id)
        session["mismatch_count"] = 0

    def reset_to_menu(self, session_id: str):
        """Force reset — user returns to role selector."""
        session = self.get_or_create(session_id)
        session["role"]           = None
        session["pending_role"]   = None
        session["mismatch_count"] = 0
        session["last_sql"]       = None
        session["last_rows"]      = []
        # Keep history so user sees what happened

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
