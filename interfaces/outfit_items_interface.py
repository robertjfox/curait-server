from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from clients.supabase_client import get_supabase_client


class OutfitItemsInterface:
    """CRUD operations for the outfit_items table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "outfit_items"

    def create(
        self,
        outfit_id: str,
        type: str,
        keywords: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new outfit item and return its ID."""
        payload: Dict[str, Any] = {
            "outfit_id": outfit_id,
            "type": type,
            "keywords": keywords,
            "search_results": [],
        }
        try:
            res = self._supabase.table(self._table).insert(payload).execute()
            return res.data[0]["id"] if res and res.data else None
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to create outfit item: {e}")
            return None

    def update_search_results(
        self, item_id: str, search_results: List[Dict[str, Any]]
    ) -> bool:
        """Update the search results for an outfit item."""
        try:
            self._supabase.table(self._table).update(
                {"search_results": search_results}
            ).eq("id", item_id).execute()
            return True
        except Exception:
            return False

    def update(
        self, 
        item_id: str, 
        type: Optional[str] = None,
        keywords: Optional[str] = None,
        search_results: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Update an outfit item's type, keywords and/or search_results."""
        try:
            updates: Dict[str, Any] = {}
            
            if type is not None:
                updates["type"] = type
            if keywords is not None:
                updates["keywords"] = keywords
            if search_results is not None:
                updates["search_results"] = search_results
            
            if not updates:
                return True  # Nothing to update
            
            self._supabase.table(self._table).update(updates).eq("id", item_id).execute()
            return True
        except Exception:
            return False

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a single outfit item by ID."""
        try:
            res = self._supabase.table(self._table).select("*").eq("id", item_id).single().execute()
            return res.data
        except Exception:
            return None

    def get_by_outfit(self, outfit_id: str) -> List[Dict[str, Any]]:
        """Get all items for an outfit."""
        try:
            res = (
                self._supabase.table(self._table)
                .select("*")
                .eq("outfit_id", outfit_id)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    def get_by_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """Get all outfit items for a thread through outfit and message relationships."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.debug(f"[DB] Querying outfit items for thread: {thread_id}")
            
            # Simplified query - get all outfit items and their related data
            res = (
                self._supabase.table(self._table)
                .select("*, outfits(*)")
                .eq("outfits.thread_id", thread_id)
                .execute()
            )
            
            items = res.data or []
            
            # Sort by creation time (most recent first)
            if items:
                items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            return items
            
        except Exception as e:
            logger.error(f"[DB] Error querying outfit items for thread {thread_id}: {e}")
            return []


