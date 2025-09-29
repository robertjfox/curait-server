import logging
import time
from typing import Dict, Any, Optional, List, Callable
from services.shopping_service import ShoppingService
from services.product_ranking_service import ProductRankingService
from interfaces.outfit_items_interface import OutfitItemsInterface
from clients.gemini_client import get_gemini_client
from interfaces.outfits_interface import OutfitsInterface
from interfaces.threads_interface import ThreadsInterface
from interfaces.users_interface import UsersInterface
from interfaces.trend_outfits_interface import TrendOutfitsInterface
from clients.openai_client import get_openai_client
import _config as config
import asyncio

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
		self.trend_outfits_interface = TrendOutfitsInterface()
		self.openai_client = get_openai_client()

	async def aclose(self):

		if self.shopping_service:
			await self.shopping_service.aclose()
		
	async def _process_single_item(
		self,
		*,				
		item_id: str,
		keywords: str,
		user_data: Dict[str, Any],
		outfit_row: Dict[str, Any],
	) -> None:
		"""Handle shopping->ranking->storage for a single item."""
		try:

			start_time = time.time()
			
			results_arr = []
			ratings_arr = []

			try:
				unranked_results, unranked_results_length, filtered_results_length = await self.shopping_service.search_for_keywords(
					keywords=keywords,
					user_data=user_data,
				)
				results_arr = unranked_results
			except Exception as e:
				logger.error(f"Failed to search for keywords '{keywords}': {e}")
				return
			
			if not unranked_results:
				return
			
			shop_time = time.time() - start_time

			self.outfit_items_interface.update_search_results(item_id, results_arr)
			
			if config.PRODUCT_RANKING_ENABLED:
				ranked_results, ratings = await self.ranking_service.rank_results(
					user_data=user_data,
					item_context={"keywords": keywords},
					results=unranked_results,
					outfit_row=outfit_row,
				)

				results_arr = ranked_results
				ratings_arr = ratings

			rank_time = time.time() - start_time - shop_time
			self.outfit_items_interface.update_search_results(item_id, results_arr)

			logger.info(
				f"🔍 {keywords}\n"
				f"  🛒 {shop_time:.1f}s | {unranked_results_length} -> {filtered_results_length} res\n"
				f"  🏆 {rank_time:.1f}s | {ratings_arr}"	
			)
			
		except Exception as e:
			logger.error(f"Failed to process item with keywords '{keywords}': {e}")

	async def _process_single_outfit(
		self,
		*,
		outfit: Dict[str, Any],
		register_callback: Callable[[Dict[str, Any], str], None],
		outfit_count: int,
		double_batch: bool = False,
		thread_id: Optional[str] = None,
	) -> None:
		"""Process a single outfit."""
		try:
			# Determine if this outfit should be cached
			should_cache = False
			if double_batch:
				# In double_batch: cache outfits 4, 5, 6 (0-indexed: 3, 4, 5)
				should_cache = outfit_count >= 4
			else:
				# In single batch: cache all outfits
				should_cache = True

			outfit_id = self.outfits_interface.create(
					name=outfit.get("name"),
					thread_id=thread_id,
					is_cached=should_cache,
				)

			for item in outfit.get("items"):
				self.outfit_items_interface.create(
					outfit_id=outfit_id,
					type=item.get("type"),
					keywords=item.get("keywords"),
				)

			# launch search and rank for the outfit (non-blocking)
			asyncio.create_task(self.search_and_rank_for_outfit(outfit_id=outfit_id))

			# Register the completed outfit
			register_callback(outfit, outfit_id)

		except Exception as e:
			logger.error(f"Failed to process outfit: {e}")
 
	async def search_and_rank_for_outfit(self, *, outfit_id: str) -> Dict[str, Any]:
		# Fetch outfit to derive thread_id and then user context
		outfit_row = self.outfits_interface.get(outfit_id)

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
			tasks.append(asyncio.create_task(self._process_single_item(
				item_id=item_id,
				keywords=keywords,
				user_data=user_data,
				outfit_row=outfit_row,
			)))

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

	async def generate_outfits_for_thread(
		self,
		thread_id: str,
	) -> Dict[str, Any]:
		"""Generate outfits for a thread with smart caching logic."""
		try:
			# Get thread info and context
			thread = self.threads_interface.get(thread_id)
			if not thread:
				return {"success": False, "error": "Thread not found"}

			user_id = thread.get("user_id")
			user_data = self.users_interface.get_relevant_context(user_id) if user_id else {}

			# Get conversation and outfit history
			conversation_history = self.threads_interface.get_conversation_history(thread_id)
			outfit_history = self.outfits_interface.get_thread_outfit_history(thread_id)

			# Check existing outfits to determine generation strategy
			existing_outfits_with_ids = self.outfits_interface.get_thread_outfits_with_ids(thread_id)
			has_existing_outfits = len(existing_outfits_with_ids) > 0

			# Get explore idea context if thread is linked to one
			explore_idea_context = None
			trend_outfits_context = None

			if thread.get("explore_idea_id"):
				explore_idea = self.threads_interface._get_explore_idea_by_id(thread.get("explore_idea_id"))
				if explore_idea:
					explore_idea_context = {
						"title": explore_idea.get("title"),
						"description": explore_idea.get("description")
					}

					# If no existing outfits, fetch trend outfits for context
					if not has_existing_outfits:
						trend_outfits_context = self.trend_outfits_interface.get_trend_outfit_context_for_prompt(thread.get("explore_idea_id"))

			if has_existing_outfits:

				# uncache all existing outfits for that thread
				for outfit in existing_outfits_with_ids:
					self.outfits_interface.update_is_cached(outfit["id"], False)

				# For existing threads: refresh cache by generating 3 new outfits
				# The _process_single_outfit will handle caching (cache all 3 since double_batch=False)
				await self._generate_outfits_batch(
					thread_id, user_id, user_data, conversation_history, outfit_history, double_batch=False, explore_idea_context=explore_idea_context, trend_outfits_context=None
				)
			else:
				# For new threads: generate 6 outfits, cache the last 3
				# The _process_single_outfit will handle caching (cache outfits 4, 5, 6 since double_batch=True)
				await self._generate_outfits_batch(
					thread_id, user_id, user_data, conversation_history, outfit_history, double_batch=True, explore_idea_context=explore_idea_context, trend_outfits_context=trend_outfits_context
				)

			return {
				"success": True,
				"action": "new_thread" if not has_existing_outfits else "refresh_cache",
				"thread_id": thread_id
			}

		except Exception as e:
			logger.error(f"Failed to generate outfits for thread {thread_id}: {e}")
			return {"success": False, "error": str(e)}

	async def _generate_outfits_batch(
		self,
		thread_id: str,
		user_id: str,
		user_data: Dict[str, Any],
		conversation_history: List[Dict[str, str]],
		outfit_history: List[Dict[str, Any]],
		double_batch: bool,
		explore_idea_context: Optional[Dict[str, Any]] = None,
		trend_outfits_context: Optional[List[Dict[str, Any]]] = None,
	) -> None:
		"""Generate a batch of outfits."""
		await self.openai_client.generate_outfits_flow(
			double_batch=double_batch,
			user_data=user_data,
			conversation_history=conversation_history,
			outfit_history=outfit_history,
			explore_idea_context=explore_idea_context,
			trend_outfits_context=trend_outfits_context,
			on_single_outfit=lambda outfit, register_callback, outfit_count: asyncio.create_task(
				self._process_single_outfit(
					outfit=outfit,
					register_callback=register_callback,
					outfit_count=outfit_count,
					double_batch=double_batch,
					thread_id=thread_id
				)
			),
			on_outfit_batch=lambda outfits, outfit_ids: self.gemini_client.launch_flatlay_task(
				outfits=outfits,
				outfit_ids=outfit_ids,
				user_id=user_id,
				thread_id=thread_id,
			),
		)

 