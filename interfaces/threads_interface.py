from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from clients.supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)

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

    def update_title(self, thread_id: str, title: str) -> bool:
        """Update the title for a thread."""
        try:
            self._supabase.table(self._table).update({
                "title": title,
            }).eq("id", thread_id).execute()
            return True
        except Exception:
            return False

    def update_thread_outfits_with_no_message_id(self, thread_id: str, message_id: str, queue_pull_count: int) -> bool:

        """Get the oldest outfits for a thread id that have no message id and give them the message id, limited by queue_pull_count."""

        logger.info(f"Updating {queue_pull_count} outfits for thread {thread_id} with message id {message_id}")

        try:
            # First get the IDs of outfits to update, then update them
            outfits_to_update = self._supabase.table("outfits").select("id").eq("thread_id", thread_id).filter("message_id", "is", "null").order("created_at", desc=False).limit(queue_pull_count).execute()
            
            if outfits_to_update.data:
                outfit_ids = [outfit["id"] for outfit in outfits_to_update.data]
                # Update the selected outfits
                res = self._supabase.table("outfits").update({"message_id": message_id}).in_("id", outfit_ids).execute()
                
                logger.info(f"Updated {len(res.data)} outfits for thread {thread_id} with message id {message_id}")
                return True
            else:
                logger.info(f"No outfits found to update for thread {thread_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update outfits: {e}")
            return False

