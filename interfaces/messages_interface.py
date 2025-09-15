from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from clients.supabase_client import get_supabase_client

MessageRole = Literal["user", "assistant", "system"]


class MessagesInterface:
    """CRUD operations for the messages table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "messages"

    def create(
        self,
        thread_id: str,
        role: MessageRole,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a new message and return its ID."""
        payload: Dict[str, Any] = {
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }
        try:
            res = self._supabase.table(self._table).insert(payload).execute()
            return res.data[0]["id"] if res and res.data else None
        except Exception:
            return None

    def get(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get a single message by ID."""
        try:
            res = self._supabase.table(self._table).select("*").eq("id", message_id).single().execute()
            return res.data
        except Exception:
            return None

    def get_by_thread(self, thread_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all messages for a thread, ordered by creation time."""
        try:
            res = (
                self._supabase.table(self._table)
                .select("*")
                .eq("thread_id", thread_id)
                .order("created_at")
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    def get_conversation_history(self, thread_id: str, limit: int = 50) -> List[Dict[str, str]]:
        """Get conversation history in OpenAI chat format (role + content only)."""
        try:
            res = (
                self._supabase.table(self._table)
                .select("role, content")
                .eq("thread_id", thread_id)
                .order("created_at")
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    def get_first_user_message(self, thread_id: str) -> Optional[str]:
        """Return the first user-authored message content for this thread, or None."""
        try:
            res = (
                self._supabase.table(self._table)
                .select("role, content")
                .eq("thread_id", thread_id)
                .eq("role", "user")
                .order("created_at")
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                return rows[0].get("content")
            return None
        except Exception:
            return None


