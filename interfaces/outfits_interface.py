from __future__ import annotations
from typing import Any, Dict, List, Optional
from clients.supabase_client import get_supabase_client

class OutfitsInterface:
    """CRUD operations for the outfits table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "outfits"

    def create(
        self,
        message_id: str,
        name: str,
        description: Optional[str] = None,
        vton_image_url: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new outfit and return its ID."""
        payload: Dict[str, Any] = {
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
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to create outfit: {e}")
            return None

    def create_outfit_data(
        self,
        message_id: str,
        parsed_outfits: Dict[str, Any],
        outfit_items_interface
    ) -> Dict[str, str]:
        """Create new outfits and their items, returning item database IDs."""
        import logging
        logger = logging.getLogger(__name__)
        
        item_db_ids: Dict[str, str] = {}
        
        try:
            for outfit_key, outfit_data in parsed_outfits.items():
                # Create outfit record
                outfit_id = self.create(
                    message_id=message_id,
                    name=outfit_data["name"],
                    description=outfit_data["description"]
                )
                
                if outfit_id:
                    # Create outfit items
                    for item_key, item_data in outfit_data["items"].items():
                        search_results = item_data.get("search_results", [])
                        
                        item_id = outfit_items_interface.create(
                            outfit_id=outfit_id,
                            type=item_data["type"],
                            keywords=item_data["keywords"],
                            search_results=search_results
                        )
                        
                        if item_id:
                            item_db_ids[f"{outfit_key}:{item_key}"] = item_id
            
        except Exception as e:
            logger.error(f"Failed to create outfit data: {e}")
            raise
            
        return item_db_ids

    def update_outfit_data(
        self,
        parsed_outfits: Dict[str, Any],
        outfit_items_interface
    ) -> Dict[str, str]:
        """Update existing outfit items in-place, returning item database IDs."""
        import logging
        logger = logging.getLogger(__name__)
        
        item_db_ids: Dict[str, str] = {}
        
        try:
            for outfit_key, outfit_data in parsed_outfits.items():
                for item_key, item_data in outfit_data["items"].items():
                    if "updated_item_id" in item_data:
                        existing_item_id = item_data["updated_item_id"]
                        item_db_ids[f"{outfit_key}:{item_key}"] = existing_item_id
                        
                        # Clear search results and update content if item was modified
                        if item_data.get("was_modified", False):
                            # Clear search results to trigger loading state
                            outfit_items_interface.update(
                                item_id=existing_item_id,
                                search_results=[]
                            )
                            
                            # Update keywords
                            outfit_items_interface.update(
                                item_id=existing_item_id,
                                keywords=item_data["keywords"]
                            )
            
        except Exception as e:
            logger.error(f"Failed to update outfit data: {e}")
            raise
            
        return item_db_ids

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
            # First get all message IDs for the thread
            messages_res = (
                self._supabase.table("messages")
                .select("id")
                .eq("thread_id", thread_id)
                .execute()
            )
            message_ids = [msg["id"] for msg in messages_res.data or []]
            
            if not message_ids:
                return []
            
            # Get outfits for those messages with their items
            res = (
                self._supabase
                .table(self._table)
                .select("name, description, outfit_items(keywords)")
                .in_("message_id", message_ids)
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

    def save_outfits_to_database(
        self,
        message_id: str,
        parsed_outfits: Dict[str, Any],
        outfit_items_interface
    ) -> Dict[str, str]:
        """Persist outfits and items, returning item database IDs for search processing."""
        import logging
        logger = logging.getLogger(__name__)
        
            
        # Use the create_outfit_data method
        logger.info(f"[SAVE] Processing new outfit creation using create_outfit_data")
        item_db_ids = self.create_outfit_data(
            message_id, parsed_outfits, outfit_items_interface
        )

        return item_db_ids
