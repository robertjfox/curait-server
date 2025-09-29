from __future__ import annotations
from typing import Any, Dict, List, Optional
from clients.supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)

class TrendOutfitsInterface:
    """CRUD operations for the trend_outfits table."""

    def __init__(self) -> None:
        self._supabase = get_supabase_client()
        self._table = "trend_outfits"

    def get_by_explore_idea(self, explore_idea_id: str) -> List[Dict[str, Any]]:
        """Get all trend outfits for an explore idea."""

        
        logger.info(f"Getting trend outfits for explore_idea_id: {explore_idea_id}")
        try:
            res = (
                self._supabase.table(self._table)
                .select("id, gender, trend_outfit_items(type, keywords)")
                .eq("explore_idea_id", explore_idea_id)
                .execute()
            )
            result = res.data or []
            logger.info(f"Found {len(result)} trend outfits for explore_idea_id: {explore_idea_id}")
            return result
        except Exception as e:
            logger.error(f"Error getting trend outfits for explore_idea_id {explore_idea_id}: {e}")
            return []

    def get_trend_outfit_context_for_prompt(self, explore_idea_id: str) -> List[Dict[str, Any]]:
        """Get trend outfit context formatted for prompt generation."""
        
        logger.info(f"Getting trend outfit context for prompt for explore_idea_id: {explore_idea_id}")
        try:
            trend_outfits = self.get_by_explore_idea(explore_idea_id)
            logger.info(f"Retrieved {len(trend_outfits)} trend outfits to format for context")
            formatted_context = []

            for outfit in trend_outfits:
                outfit_id = outfit.get("id")
                logger.info(f"Processing trend outfit {outfit_id}")
                outfit_context = {
                    "trend_outfit_id": outfit_id,
                    "items": []
                }

                # Extract items from the outfit
                items = outfit.get("trend_outfit_items", [])
                logger.info(f"Trend outfit {outfit_id} has {len(items)} items")
                for item in items:
                    outfit_context["items"].append({
                        "type": item.get("type"),
                        "keywords": item.get("keywords")
                    })

                if outfit_context["items"]:
                    formatted_context.append(outfit_context)
                    logger.info(f"Added trend outfit {outfit_id} to formatted context")
                else:
                    logger.info(f"Skipped trend outfit {outfit_id} - no valid items")

            logger.info(f"Formatted {len(formatted_context)} trend outfits for context")
            return formatted_context
        except Exception as e:
            logger.error(f"Error getting trend outfit context for explore_idea_id {explore_idea_id}: {e}")
            return []
