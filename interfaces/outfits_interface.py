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
        vton_image_url: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new outfit and return its ID."""
        payload: Dict[str, Any] = {
            "thread_id": thread_id,
            "message_id": message_id,
            "name": name,
            "description": description,
            "vton_image_url": vton_image_url,
        }
        try:
            res = self._supabase.table(self._table).insert(payload).execute()
            return res.data[0]["id"] if res and res.data else None
        except Exception as e:
            import logging

            logger.error(f"Failed to create outfit: {e}")
            return None

    def create_outfits_and_items(
        self,
        *,
        thread_id: str,
        assistant_msg_id: str,
        num_outfits: int,
        num_items: int,
        queue_multiplier: int,
    ) -> Tuple[List[str], List[str]]:
        """Create empty outfit and item stubs in the database."""
        outfit_ids: List[str] = []
        item_db_ids: List[str] = []

        # Calculate total outfits to create
        total_outfits = num_outfits * queue_multiplier

        if queue_multiplier == 1:
            assistant_msg_id = None

        for i in range(total_outfits):
            # Only link first batch of outfits to the message
            msg_id = assistant_msg_id if i < num_outfits else None

            # Create empty outfit stub
            new_outfit_id = self.create(
                thread_id=thread_id,
                message_id=msg_id,
                name="",
                description="",
            )
            outfit_ids.append(new_outfit_id)

            # Create empty item stubs for this outfit
            for _ in range(num_items):
                item_id = self.outfit_items_interface.create(
                    outfit_id=new_outfit_id,
                    type="unknown",
                    keywords="",
                )
                item_db_ids.append(item_id)

        return outfit_ids, item_db_ids  

    def update_vton_image(self, outfit_id: str, vton_image_url: str) -> bool:
        """Update the virtual try-on image URL for an outfit."""
        try:
            self._supabase.table(self._table).update(
                {"vton_image_url": vton_image_url}
            ).eq("id", outfit_id).execute()
            return True
        except Exception:
            return False

    def update_outfit_metadata(self, outfit_id: str, name: str, description: str) -> bool:
        """Update the name and description for an outfit."""
        try:
            updates = {}
            if name:
                updates["name"] = name
            if description:
                updates["description"] = description
            
            if updates:
                self._supabase.table(self._table).update(updates).eq("id", outfit_id).execute()
            return True
        except Exception:
            return False

    def get_thread_outfit_history(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all outfit history for a thread with title, description, and keywords."""
        try:
            # Get outfits directly by thread_id with their items
            res = (
                self._supabase
                .table(self._table)
                .select("name, description, outfit_items(keywords)")
                .eq("thread_id", thread_id)
                .execute()
            )
            
            outfits = []
            for outfit in res.data or []:
                # Collect all keywords from outfit items
                all_keywords = []
                for item in outfit.get("outfit_items", []):
                    if item.get("keywords"):
                        all_keywords.append(item["keywords"])
                
                outfits.append({
                    "title": outfit.get("name"),
                    "description": outfit.get("description"),
                    "keywords": all_keywords
                })
            
            return outfits
        except Exception:
            return []

    def update_multiple_outfits_metadata(
        self,
        outfit_metadata: Dict[str, Any],
        outfit_ids: List[str],
        item_db_ids: List[str],
        num_items: int,
    ) -> None:
        """Update outfits from the new shape: {"outfits": [{name, description, items:[{type,keywords}], default_rendering_url?}]}"""
        outfits: List[Dict[str, Any]] = (outfit_metadata.get("outfits") or [])[:len(outfit_ids)]
        for index, (outfit_id, outfit) in enumerate(zip(outfit_ids, outfits)):
            self.update_outfit_metadata(
                outfit_id=outfit_id,
                name=outfit.get("name", ""),
                description=outfit.get("description", ""),
            )

            # Optional: set default_rendering_url if provided
            default_url = outfit.get("default_rendering_url")
            if default_url:
                try:
                    self._supabase.table(self._table).update(
                        {"default_rendering_url": default_url}
                    ).eq("id", outfit_id).execute()
                except Exception:
                    pass

            start = index * num_items
            ids_slice = item_db_ids[start:start + num_items]
            items: List[Dict[str, Any]] = (outfit.get("items") or [])[:num_items]
            for item_id, item in zip(ids_slice, items):
                self.outfit_items_interface.update(
                    item_id=item_id,
                    type=item.get("type", ""),
                    keywords=item.get("keywords", ""),
                )

    def update_default_rendering_url(self, outfit_id: str, url: str) -> bool:
        """Set the default rendering URL (flatlay) for an outfit."""
        try:
            self._supabase.table(self._table).update(
                {"default_rendering_url": url}
            ).eq("id", outfit_id).execute()
            return True
        except Exception:
            return False