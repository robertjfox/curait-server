import logging
import asyncio
from typing import Dict, Any, Optional, List
from clients.openai_client import get_openai_client
from services.shopping_service import ShoppingService
from services.product_ranking_service import ProductRankingService
from interfaces.outfit_items_interface import OutfitItemsInterface
from interfaces.outfits_interface import OutfitsInterface
from utils.image_processing.background_removal import SupabaseBackgroundProcessor

import _config

logger = logging.getLogger(__name__)


class OutfitGenerationService:
	"""
	Responsible for LLM-driven outfit idea generation and parsing.
	Now also handles the parallel shopping->ranking->storage flow for each item.
	"""

	def __init__(self):
		self.openai_client = get_openai_client()
		self.shopping_service = ShoppingService()
		self.ranking_service = ProductRankingService()
		self.outfit_items_interface = OutfitItemsInterface()
		self.outfits_interface = OutfitsInterface()
		self._processed_items = set()  # Track which items have been processed

	async def aclose(self):
		"""Clean up resources."""
		if self.shopping_service:
			await self.shopping_service.aclose()

	async def apply_modifications_to_existing_items(
		self,
		existing_items: List[Dict[str, Any]],	# items that are already in the outfit (from the DB)
		modified_items: List[Dict[str, Any]],
		user_data: Dict[str, Any],
		thread_id: Optional[str] = None,
	) -> None:
		"""Map modification keywords to existing item IDs and search for new products."""

		# Create lookup for existing items by type
		type_to_item_id: Dict[str, str] = {}
		for item in existing_items:
			item_type = item.get("type")
			type_to_item_id[item_type] = item["id"]

		# Map modified items to their corresponding existing item IDs
		item_keywords_map: Dict[str, str] = {}

		for mod in modified_items:
			item_type = mod.get("type")
			keywords = (mod.get("keywords") or "").strip()
			
			# Skip if we don't have valid data or no item of this type
			if not item_type or not keywords or item_type not in type_to_item_id:
				continue
				
			# Get the item ID for this type
			item_id = type_to_item_id[item_type]
			item_keywords_map[item_id] = keywords
			
		tasks = []
		for item_id, keywords in item_keywords_map.items():
			tasks.append(self._process_single_item(
				item_id=item_id,
				keywords=keywords,
				user_data=user_data,
				thread_id=thread_id
			))
		if tasks:
			await asyncio.gather(*tasks, return_exceptions=True)
		
	async def _process_single_item(
		self,
		item_id: str,
		keywords: str,
		user_data: Dict[str, Any],
		thread_id: Optional[str] = None
	) -> None:
		"""Handle shopping->ranking->storage for a single item."""
		try:
			# Step 1: Shopping
			raw_results = await self.shopping_service.search_for_keywords(
				keywords=keywords,
				user_data=user_data,
				thread_id=thread_id
			)
			
			if not raw_results:
				return
			
			# Update with raw results first
			self.outfit_items_interface.update_search_results(item_id, raw_results)
			
			# Step 2: Ranking
			if _config.PRODUCT_RANKING_ENABLED:
				ranked_results = await self.ranking_service.rank_results(
					user_data=user_data,
					item_context={"keywords": keywords},
					results=raw_results,
					thread_id=thread_id,
				)
			else:
				ranked_results = raw_results

			# Step 3: Background removal
			if ranked_results and getattr(_config, "BACKGROUND_REMOVAL_ENABLED", False) and ranked_results[0].get("imageUrl"):
				async with SupabaseBackgroundProcessor() as processor:
					ranked_results[0]["imageUrl"] = await processor.process_image(ranked_results[0]["imageUrl"])
			
			# Step 4: Storage
			self.outfit_items_interface.update_search_results(item_id, ranked_results)
			
		except Exception as e:
			logger.error(f"Failed to process item with keywords '{keywords}': {e}")

 