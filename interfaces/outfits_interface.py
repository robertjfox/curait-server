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
        message_id: str,
        name: str,
        description: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new outfit and return its ID."""
        payload: Dict[str, Any] = {
            "thread_id": thread_id,
            "message_id": message_id,
            "name": name,
            "description": description,
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
        """Get all outfit history for a thread with title, description, keywords, and feedback."""
        try:
            # Get outfits directly by thread_id with their items
            res = (
                self._supabase
                .table(self._table)
                .select("name, description, feedback, outfit_items(keywords, feedback)")
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
                    "description": outfit.get("description"),
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