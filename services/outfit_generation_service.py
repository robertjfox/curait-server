import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, Any, List, Optional
from services.shopping_service import ShoppingService
from services.product_ranking_service import ProductRankingService
from interfaces.outfit_items_interface import OutfitItemsInterface
from utils.image_processing.background_removal import SupabaseBackgroundProcessor
import _config as config

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

			# Step 3: BACKGROUND REMOVAL
			if ranked_results and config.BACKGROUND_REMOVAL_ENABLED and ranked_results[0].get("imageUrl"):
				async with SupabaseBackgroundProcessor() as processor:
					ranked_results[0]["imageUrl"] = await processor.process_image(ranked_results[0]["imageUrl"])
			
			# Step 4: STORAGE
			self.outfit_items_interface.update_search_results(item_id, ranked_results)

			logger.info(
				f"🔍 {keywords}\n"
				f"  🛒 {shop_time:.1f}s | {unfiltered_results_length} results\n"
				f"  🏆 {rank_time:.1f}s | {ratings}"	
			)
			
		except Exception as e:
			logger.error(f"Failed to process item with keywords '{keywords}': {e}")

 