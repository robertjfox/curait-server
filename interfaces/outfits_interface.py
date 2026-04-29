from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from clients.supabase_client import get_supabase_client
from interfaces.outfit_items_interface import OutfitItemsInterface

import logging
logger = logging.getLogger(__name__)


class OutfitsInterface:
    """CRUD operations for the outfits table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "outfits"
        self.outfit_items_interface = OutfitItemsInterface()

    def create(
        self,
        thread_id: str,
        name: str,
        is_cached: bool = False,
    ) -> Optional[str]:
        """Create a new outfit and return its ID."""
        payload: Dict[str, Any] = {
            "thread_id": thread_id,
            "name": name,
            "is_cached": is_cached,
        }
        try:
            res = self._supabase.table(self._table).insert(payload).execute()
            return res.data[0]["id"] if res and res.data else None
        except Exception as e:
            import logging

            logger.error(f"Failed to create outfit: {e}")
            return None

    def update_vton_image(self, outfit_id: str, vton_image_url: str) -> bool:
        """Update the virtual try-on image URL for an outfit."""
        try:
            self._supabase.table(self._table).update(
                {"vton_image_url": vton_image_url}
            ).eq("id", outfit_id).execute()
            return True
        except Exception:
            return False

    def get_thread_outfit_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all outfit history for a thread with title, keywords, and feedback."""
        try:
            # Get outfits directly by thread_id with their items
            res = (
                self._supabase
                .table(self._table)
                .select("name, feedback, outfit_items(keywords, feedback)")
                .eq("thread_id", thread_id)
                .execute()
            )
            
            outfits = []
            for outfit in res.data or []:
                # Collect keywords with their corresponding feedback
                items_with_feedback = []
                for item in outfit.get("outfit_items", []):
                    item_data = {}
                    if item.get("keywords"):
                        item_data["keywords"] = item["keywords"]
                    if item.get("feedback"):
                        item_data["feedback"] = item["feedback"]
                    
                    if item_data:  # Only add if there's data
                        items_with_feedback.append(item_data)
                
                outfits.append({
                    "title": outfit.get("name"),
                    "items": items_with_feedback,  # Each item has its keywords and feedback paired
                    "feedback": outfit.get("feedback")  # Overall outfit feedback
                })
            
            return outfits
        except Exception:
            return []

    def update_default_rendering_url(self, outfit_id: str, url: str) -> bool:
        """Set the default rendering URL (flatlay) for an outfit."""
        try:
            self._supabase.table(self._table).update(
                {"default_rendering_url": url}
            ).eq("id", outfit_id).execute()
            return True
        except Exception:
            return False

    def get(self, outfit_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single outfit row by ID."""
        try:
            res = (
                self._supabase
                .table(self._table)
                .select("*")
                .eq("id", outfit_id)
                .single()
                .execute()
            )
            return res.data
        except Exception:
            return None

    def update_is_cached(self, outfit_id: str, is_cached: bool) -> bool:
        """Update the is_cached flag for an outfit."""
        try:
            self._supabase.table(self._table).update(
                {"is_cached": is_cached}
            ).eq("id", outfit_id).execute()
            return True
        except Exception:
            return False

    def set_saved(self, outfit_id: str, saved: bool) -> Optional[Dict[str, Any]]:
        """Set the saved flag for an outfit and return the updated row."""
        try:
            res = (
                self._supabase
                .table(self._table)
                .update({"saved": saved})
                .eq("id", outfit_id)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Failed to update saved state for outfit {outfit_id}: {e}")
            return None

    def list_saved_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all saved outfits for a user, including products."""
        try:
            res = (
                self._supabase
                .table(self._table)
                .select("*, outfit_items (*), threads!inner(user_id)")
                .eq("threads.user_id", user_id)
                .eq("saved", True)
                .order("updated_at", desc=True)
                .execute()
            )
            outfits = res.data or []
            for outfit in outfits:
                outfit.pop("threads", None)
            return outfits
        except Exception as e:
            logger.error(f"Failed to list saved outfits for user {user_id}: {e}")
            return []

    def get_next_cached_for_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Return the oldest cached outfit for a thread."""
        try:
            res = (
                self._supabase
                .table(self._table)
                .select("*")
                .eq("thread_id", thread_id)
                .eq("is_cached", True)
                .order("created_at")
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            return None

    def get_thread_outfits_with_ids(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all outfits for a thread with their IDs and is_cached status."""
        try:
            res = (
                self._supabase
                .table(self._table)
                .select("id, name, is_cached, created_at")
                .eq("thread_id", thread_id)
                .order("created_at")
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    def list_for_thread_with_items(self, thread_id: str) -> List[Dict[str, Any]]:
        """Return all outfits for a thread, including their items, ordered for UI display."""
        try:
            res = (
                self._supabase
                .table(self._table)
                .select("*, outfit_items (*)")
                .eq("thread_id", thread_id)
                .order("outfit_order")
                .order("created_at")
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to list outfits for thread {thread_id}: {e}")
            return []