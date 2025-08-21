import logging
import asyncio
from typing import Dict, Any, Optional, List
from clients.openai_client import get_openai_client
from services.shopping_service import ShoppingService
from services.product_ranking_service import ProductRankingService
from interfaces.outfit_items_interface import OutfitItemsInterface
from interfaces.outfits_interface import OutfitsInterface

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
		outfit_id: str,
		modified_items: List[Dict[str, Any]],
		user_data: Dict[str, Any],
		thread_id: Optional[str] = None,
	) -> None:
		"""Map modification keywords to existing item IDs and search for new products."""
		existing_items = self.outfit_items_interface.get_by_outfit(outfit_id)

		# Group existing items by type for easy lookup
		type_to_item_ids: Dict[str, List[str]] = {}
		for item in existing_items:
			item_type = item.get("type")
			if item_type:
				type_to_item_ids.setdefault(item_type, []).append(item["id"])

		# Map modified items to their corresponding existing item IDs
		item_keywords_map: Dict[str, str] = {}
		for modification in modified_items:
			item_type = modification.get("type")
			keywords = (modification.get("keywords") or "").strip()
			
			# Skip if we don't have valid data or no items of this type
			if not item_type or not keywords or not type_to_item_ids.get(item_type):
				continue
				
			# Get the next available item ID of this type
			item_id = type_to_item_ids[item_type].pop(0)
			item_keywords_map[item_id] = keywords
			
		await self.process_item_keywords(
			item_keywords_map=item_keywords_map,
			user_data=user_data,
			thread_id=thread_id,
		)



	async def process_keywords_with_item_ids(
		self,
		item_db_ids: Dict[str, str],
		keywords: List[str],
		user_data: Dict[str, Any],
		thread_id: Optional[str] = None
	) -> None:
		"""Process keywords using existing item IDs from early DB creation."""
		try:
			logger.info(f"🔍 Processing {len(keywords)} keywords with item_db_ids: {item_db_ids}")
			logger.info(f"🔍 Keywords to process: {keywords}")
			# Map keywords to item IDs in the correct order across all outfits
			import _config
			num_outfits = getattr(_config, "NUM_OUTFITS_TO_GENERATE", 1)
			num_items = getattr(_config, "NUM_ITEMS_PER_OUTFIT", 1)
			
			item_keywords_map: Dict[str, str] = {}
			
			# Find the next unprocessed items to assign these keywords to
			available_items = []
			for outfit_num in range(1, num_outfits + 1):
				for item_num in range(1, num_items + 1):
					key = f"outfit_{outfit_num}:item_{item_num}"
					if key in item_db_ids:
						item_id = item_db_ids[key]
						if item_id not in self._processed_items:
							available_items.append((key, item_id))
			
			# Map keywords to available items
			for idx, keyword in enumerate(keywords):
				if idx < len(available_items):
					key, item_id = available_items[idx]
					item_keywords_map[item_id] = keyword
					self._processed_items.add(item_id)  # Mark as processed
					logger.debug(f"🎯 Mapped keyword {idx + 1}: '{keyword}' → {key} ({item_id})")
			
			logger.info(f"🎯 Final item_keywords_map: {item_keywords_map}")
			logger.info(f"🎯 Mapped {len(item_keywords_map)} items out of {len(keywords)} keywords")
			
			# Process search for all items
			await self.process_item_keywords(
				item_keywords_map=item_keywords_map,
				user_data=user_data,
				thread_id=thread_id,
			)
		except Exception as e:
			logger.error(f"Failed to process keywords with item IDs: {e}")

	async def update_outfits_with_final_data(
		self,
		item_db_ids: Dict[str, str],
		parsed_outfits: Dict[str, Any]
	) -> None:
		"""Update existing outfit items with final parsed data (names, descriptions, types)."""
		try:
			logger.debug(f"Updating outfits with final data. Item DB IDs: {item_db_ids}")
			logger.debug(f"Parsed outfits structure: {list(parsed_outfits.keys())}")
			for outfit_key, outfit_data in parsed_outfits.items():
				# Update outfit name and description
				# Find the outfit_id from the first item in this outfit
				first_item_key = f"{outfit_key}:item_1"
				if first_item_key in item_db_ids:
					first_item_id = item_db_ids[first_item_key]
					# Get the outfit_id from the item
					item_data = self.outfit_items_interface.get(first_item_id)
					if item_data and item_data.get("outfit_id"):
						outfit_id = item_data["outfit_id"]
						# Update outfit with final name and description
						self.outfits_interface.update_outfit_metadata(
							outfit_id=outfit_id,
							name=outfit_data.get("name", ""),
							description=outfit_data.get("description", "")
						)
				
				# Update each item with proper type and keywords
				# Items are directly in outfit_data with keys like "item_1", "item_2", etc.
				for key, value in outfit_data.items():
					if key.startswith("item_") and isinstance(value, dict):
						db_key = f"{outfit_key}:{key}"
						if db_key in item_db_ids:
							item_id = item_db_ids[db_key]
							# Update item with final type and refined keywords
							self.outfit_items_interface.update(
								item_id=item_id,
								type=value.get("type", "unknown"),
								keywords=value.get("keywords", "")
							)
		except Exception as e:
			logger.error(f"Failed to update outfits with final data: {e}")

	async def process_item_keywords(
		self,
		item_keywords_map: Dict[str, str],
		user_data: Dict[str, Any],
		thread_id: Optional[str] = None
	) -> None:
		"""For each item_id and its keywords, run shopping->ranking->store."""
		logger.info(f"🛍️ Starting search for {len(item_keywords_map)} items")
		for item_id, keywords in item_keywords_map.items():
			logger.info(f"🛍️ Will search item {item_id}: '{keywords}'")
		
		tasks = []
		for item_id, keywords in (item_keywords_map or {}).items():
			tasks.append(self._process_single_item(
				item_id=item_id,
				keywords=keywords,
				user_data=user_data,
				thread_id=thread_id
			))
		
		if tasks:
			await asyncio.gather(*tasks, return_exceptions=True)
		else:
			logger.info("[SEARCH] No items to process")

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
			ranked_results = await self.ranking_service.rank_results(
				user_data=user_data,
				item_context={"keywords": keywords},
				results=raw_results,
				thread_id=thread_id,
			)
			
			# Step 3: Storage
			self.outfit_items_interface.update_search_results(item_id, ranked_results)
			
		except Exception as e:
			logger.error(f"Failed to process item with keywords '{keywords}': {e}")

 