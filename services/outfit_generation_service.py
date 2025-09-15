import logging
import time
from typing import Dict, Any, Optional, List
from services.shopping_service import ShoppingService
from services.product_ranking_service import ProductRankingService
from interfaces.outfit_items_interface import OutfitItemsInterface
from utils.image_processing.background_removal import SupabaseBackgroundProcessor
import _config as config
from clients.gemini_client import get_gemini_client
from interfaces.outfits_interface import OutfitsInterface
import asyncio
from interfaces.threads_interface import ThreadsInterface
from interfaces.users_interface import UsersInterface

logger = logging.getLogger(__name__)


class OutfitGenerationService:
	"""
	Simplified outfit generation service focused on:
	1. Shopping for items based on keywords
	2. Ranking search results using vision models 
	3. Storing results in the database
	"""

	def __init__(self, max_concurrency: Optional[int] = None):
		self.shopping_service = ShoppingService(max_concurrency=max_concurrency)
		self.ranking_service = ProductRankingService()
		self.outfit_items_interface = OutfitItemsInterface()
		self.outfits_interface = OutfitsInterface()
		self.gemini_client = get_gemini_client()
		self.threads_interface = ThreadsInterface()
		self.users_interface = UsersInterface()

	async def aclose(self):

		if self.shopping_service:
			await self.shopping_service.aclose()
		
	async def _process_single_item(
		self,
		item_id: str,
		keywords: str,
		user_data: Dict[str, Any],
		thread_id: Optional[str] = None,
	) -> None:
		"""Handle shopping->ranking->storage for a single item."""
		try:

			start_time = time.time()

			# Step 1: SHOPPING ------------------------------------------------------------

			try:
				raw_results, unfiltered_results_length = await self.shopping_service.search_for_keywords(
					keywords=keywords,
					user_data=user_data,
					thread_id=thread_id
				)
			except Exception as e:
				logger.error(f"Failed to search for keywords '{keywords}': {e}")
				return
			
			if not raw_results:
				return
			
			shop_time = time.time() - start_time

			# Update with raw results first
			self.outfit_items_interface.update_search_results(item_id, raw_results)
			
			# Step 2: RANKING ------------------------------------------------------------		
			
			if config.PRODUCT_RANKING_ENABLED:
				ranked_results, ratings = await self.ranking_service.rank_results(
					user_data=user_data,
					item_context={"keywords": keywords},
					results=raw_results,
					thread_id=thread_id,
				)
			else:
				ranked_results = raw_results

			rank_time = time.time() - start_time - shop_time
			# Step 4: STORAGE
			self.outfit_items_interface.update_search_results(item_id, ranked_results)

			logger.info(
				f"🔍 {keywords}\n"
				f"  🛒 {shop_time:.1f}s | {unfiltered_results_length} results\n"
				f"  🏆 {rank_time:.1f}s | {ratings}"	
			)
			
		except Exception as e:
			logger.error(f"Failed to process item with keywords '{keywords}': {e}")

 
	async def process_multiple_outfits(
			self, *, 
			outfits: List[Dict[str, Any]], 
			thread_id: Optional[str] = None, 
			user_gender: Optional[str] = None,
			assistant_msg_id: Optional[str] = None,
		) -> None:
		"""Update outfit metadata, update outfit_items with types/keywords, and launch flatlay generation for all outfits."""
		try:

			# create outfit and items in the database
			outfit_ids = []

			for outfit in outfits:
				outfit_id = self.outfits_interface.create(
					thread_id=thread_id,
					message_id=assistant_msg_id,
					name=outfit.get("name"),
					description=outfit.get("description"),
				)

				outfit_ids.append(outfit_id)
				for item in outfit.get("items"):
					self.outfit_items_interface.create(
						outfit_id=outfit_id,
						type=item.get("type"),
						keywords=item.get("keywords"),
					)

			# Launch flatlay generation for ALL outfits after metadata is set
			self.gemini_client.launch_flatlay_task(outfits, thread_id=thread_id, outfit_ids=outfit_ids, user_gender=user_gender)

		except Exception as e:
			logger.warning(f"Failed to process multiple outfits: {e}")

 
	async def search_and_rank_for_outfit(self, *, outfit_id: str) -> Dict[str, Any]:
		"""Trigger product search and ranking for all items in a given outfit in parallel.

		Returns a summary dict with counts.
		"""
		# Fetch outfit to derive thread_id and then user context
		outfit_row = self.outfits_interface.get(outfit_id)
		if not outfit_row:
			return {"success": False, "message": "Outfit not found"}

		thread_id: Optional[str] = outfit_row.get("thread_id")
		user_data: Dict[str, Any] = {}
		try:
			if thread_id:
				thread = self.threads_interface.get(thread_id)
				user_id = thread.get("user_id") if thread else None
				if user_id:
					user_data = self.users_interface.get_relevant_context(user_id) or {}
		except Exception:
			user_data = {}

		# Fetch items for the outfit
		items = self.outfit_items_interface.get_by_outfit(outfit_id)
		if not items:
			return {"success": True, "items_processed": 0}

		# Build tasks for items that have keywords
		tasks: List[asyncio.Task] = []
		for item in items:
			item_id = item.get("id")
			keywords = (item.get("keywords") or "").strip()
			if not item_id or not keywords:
				continue
			tasks.append(asyncio.create_task(self._process_single_item(item_id, keywords, user_data, thread_id)))

		if not tasks:
			return {"success": True, "items_processed": 0}

		# Execute in parallel
		results = await asyncio.gather(*tasks, return_exceptions=True)

		errors = sum(1 for r in results if isinstance(r, Exception))
		return {
			"success": errors == 0,
			"items_processed": len(tasks),
			"errors": errors,
		}

 