from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from clients.supabase_client import get_supabase_client


class ThreadsInterface:
    """CRUD operations for the threads table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "threads"

    def create(
        self,
        user_id: str,
    ) -> Optional[str]:
        """Create a new thread and return its ID."""
        payload: Dict[str, Any] = {
            "user_id": user_id,
        }
        try:
            res = self._supabase.table(self._table).insert(payload).execute()
            return res.data[0]["id"] if res and res.data else None
        except Exception:
            return None

    def get(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Get a single thread by ID."""
        try:
            res = self._supabase.table(self._table).select("*").eq("id", thread_id).single().execute()
            return res.data
        except Exception:
            return None

    def update_context(self, thread_id: str, context: Dict[str, Any]) -> bool:
        """Update the context for a thread."""
        try:
            self._supabase.table(self._table).update({
                "context": context,
                "updated_at": datetime.now().isoformat(),
            }).eq("id", thread_id).execute()
            return True
        except Exception:
            return False





