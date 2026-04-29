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
from clients.openai_client import get_openai_client
import _config as config
import asyncio
from utils.background_tasks import spawn

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
			logger.info(f"🔎 Searching products: {keywords}")
			
			results_arr = []
			ratings_arr = []

			try:
				unranked_results, unranked_results_length, filtered_results_length = await self.shopping_service.search_for_keywords(
					keywords=keywords,
					user_data=user_data,
				)
				results_arr = unranked_results
			except asyncio.CancelledError:
				raise
			except Exception as e:
				logger.error(f"Failed to search for keywords '{keywords}': {e}")
				return
			
			if not unranked_results:
				logger.info(
					f"🔍 {keywords}\n"
					f"  🛒 no products found | {unranked_results_length} -> {filtered_results_length} res"
				)
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
			
		except asyncio.CancelledError:
			raise
		except Exception as e:
			logger.error(f"Failed to process item with keywords '{keywords}': {e}")

	async def _process_single_outfit(
		self,
		*,
		outfit: Dict[str, Any],
		register_callback: Callable[[Dict[str, Any], str], None],
		outfit_count: int,
		double_batch: bool = False,
		force_cached: bool = False,
		thread_id: Optional[str] = None,
	) -> None:
		"""Process a single outfit."""
		try:
			# Determine if this outfit should be cached
			should_cache = False
			if force_cached:
				should_cache = True
			elif double_batch:
				# Keep the first generated frame visible and hold the rest in reserve.
				should_cache = outfit_count > config.NUM_OUTFITS_IN_GRID
			else:
				should_cache = False

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

			# Gemini only needs the outfit idea and DB id. Start rendering before
			# slower product search/ranking so image generation overlaps with them.
			register_callback(outfit, outfit_id)

			spawn(
				self.search_and_rank_for_outfit(outfit_id=outfit_id),
				name=f"search-rank:{(thread_id or 'unknown')[:6]}:{outfit_count}",
			)

		except asyncio.CancelledError:
			raise
		except Exception as e:
			logger.error(f"Failed to process outfit: {e}")
 
	async def search_and_rank_for_outfit(self, *, outfit_id: str) -> Dict[str, Any]:
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

	async def _search_and_rank_item_ids(
		self,
		*,
		outfit_id: str,
		item_ids: List[str],
		user_data: Dict[str, Any],
	) -> Dict[str, Any]:
		outfit_row = self.outfits_interface.get(outfit_id)
		if not outfit_row:
			return {"success": False, "message": "Outfit not found"}

		item_id_set = set(item_ids)
		items = [
			item
			for item in self.outfit_items_interface.get_by_outfit(outfit_id)
			if item.get("id") in item_id_set
		]
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

		results = await asyncio.gather(*tasks, return_exceptions=True)
		errors = sum(1 for r in results if isinstance(r, Exception))
		return {
			"success": errors == 0,
			"items_processed": len(tasks),
			"errors": errors,
		}

	async def remix_outfit(self, *, outfit_id: str, feedback: str) -> Dict[str, Any]:
		feedback = (feedback or "").strip()
		if not feedback:
			return {"success": False, "message": "Feedback is required"}

		existing_outfit = self.outfits_interface.get(outfit_id)
		if not existing_outfit:
			return {"success": False, "message": "Outfit not found"}

		thread_id: Optional[str] = existing_outfit.get("thread_id")
		if not thread_id:
			return {"success": False, "message": "Outfit thread not found"}

		thread = self.threads_interface.get(thread_id)
		user_id = thread.get("user_id") if thread else None
		user_data = self.users_interface.get_relevant_context(user_id) if user_id else {}
		existing_items = self.outfit_items_interface.get_by_outfit(outfit_id)
		items_by_id = {item.get("id"): item for item in existing_items if item.get("id")}

		remix = await self.openai_client.generate_remix_outfit_flow(
			user_data=user_data or {},
			existing_outfit=existing_outfit,
			existing_items=existing_items,
			feedback=feedback,
		)

		new_outfit_id = self.outfits_interface.create(
			thread_id=thread_id,
			name=remix.get("name") or f"{existing_outfit.get('name') or 'Outfit'} Remix",
			is_cached=True,
		)
		if not new_outfit_id:
			return {"success": False, "message": "Failed to create remixed outfit"}

		changed_item_ids: List[str] = []
		new_items_for_image: List[Dict[str, Any]] = []

		for planned_item in remix.get("items", []):
			item_type = planned_item.get("type")
			keywords = planned_item.get("keywords")
			action = planned_item.get("action")
			source_item = items_by_id.get(planned_item.get("source_item_id"))
			should_reuse = action == "keep" and source_item is not None

			if should_reuse:
				item_type = source_item.get("type") or item_type
				keywords = source_item.get("keywords") or keywords

			new_item_id = self.outfit_items_interface.create(
				outfit_id=new_outfit_id,
				type=item_type,
				keywords=keywords,
			)
			if not new_item_id:
				continue

			if should_reuse:
				search_results = source_item.get("search_results") or []
				if search_results:
					self.outfit_items_interface.update_search_results(new_item_id, search_results)
			else:
				changed_item_ids.append(new_item_id)

			new_items_for_image.append({
				"type": item_type,
				"keywords": keywords,
			})

		image_outfit = {
			"name": remix.get("name") or existing_outfit.get("name") or "Remixed outfit",
			"items": new_items_for_image,
			"remix_feedback": feedback,
		}

		if changed_item_ids:
			spawn(
				self._search_and_rank_item_ids(
					outfit_id=new_outfit_id,
					item_ids=changed_item_ids,
					user_data=user_data or {},
				),
				name=f"remix-search:{thread_id[:6]}",
			)

		if user_id:
			self.gemini_client.launch_flatlay_task(
				outfits=[image_outfit],
				outfit_ids=[new_outfit_id],
				user_id=user_id,
				thread_id=thread_id,
			)

		return {
			"success": True,
			"thread_id": thread_id,
			"outfit_id": new_outfit_id,
			"changed_items": len(changed_item_ids),
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

			await self._generate_outfits_batch(
				thread_id, user_id, user_data, conversation_history, outfit_history, double_batch=True,
			)

			return {
				"success": True,
				"thread_id": thread_id,
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
		force_cached: bool = False,
	) -> None:
		"""Generate a batch of outfits."""
		await self.openai_client.generate_outfits_flow(
			double_batch=double_batch,
			user_data=user_data,
			conversation_history=conversation_history,
			outfit_history=outfit_history,
			on_single_outfit=lambda outfit, register_callback, outfit_count: spawn(
				self._process_single_outfit(
					outfit=outfit,
					register_callback=register_callback,
					outfit_count=outfit_count,
					double_batch=double_batch,
					force_cached=force_cached,
					thread_id=thread_id
				),
				name=f"process-outfit:{thread_id[:6]}:{outfit_count}",
			),
			on_outfit_batch=lambda outfits, outfit_ids: self.gemini_client.launch_flatlay_task(
				outfits=outfits,
				outfit_ids=outfit_ids,
				user_id=user_id,
				thread_id=thread_id,
			),
		)

	async def reveal_next_cached_outfit(self, *, thread_id: str) -> Dict[str, Any]:
		thread = self.threads_interface.get(thread_id)
		if not thread:
			return {"success": False, "message": "Thread not found"}

		cached_outfit = self.outfits_interface.get_next_cached_for_thread(thread_id)
		if cached_outfit:
			self.outfits_interface.update_is_cached(cached_outfit["id"], False)

		user_id = thread.get("user_id")
		user_data = self.users_interface.get_relevant_context(user_id) if user_id else {}
		conversation_history = self.threads_interface.get_conversation_history(thread_id)
		outfit_history = self.outfits_interface.get_thread_outfit_history(thread_id)

		spawn(
			self._generate_outfits_batch(
				thread_id,
				user_id,
				user_data or {},
				conversation_history,
				outfit_history,
				double_batch=False,
				force_cached=True,
			),
			name=f"refill-cache:{thread_id[:6]}",
		)

		return {
			"success": True,
			"thread_id": thread_id,
			"outfit_id": cached_outfit.get("id") if cached_outfit else None,
			"revealed": bool(cached_outfit),
		}

 