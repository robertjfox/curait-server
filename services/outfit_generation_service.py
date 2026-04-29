import logging
import time
import asyncio
from typing import Dict, Any, Optional, List, Callable

from services.shopping_service import get_shopping_service
from services.product_ranking_service import ProductRankingService
from clients.gemini_client import get_gemini_client
from clients.openai_client import get_openai_client
from interfaces import db, aexec
import _config as config
from utils.background_tasks import spawn

logger = logging.getLogger(__name__)

_outfit_generation_semaphore = asyncio.Semaphore(
	max(1, int(config.OUTFIT_GENERATION_CONCURRENCY))
)
_search_rank_outfit_semaphore = asyncio.Semaphore(
	max(1, int(config.SEARCH_RANK_OUTFIT_CONCURRENCY))
)


class OutfitGenerationService:
	"""Coordinates outfit generation, product search, ranking, and image rendering.

	All Supabase I/O runs through :func:`aexec` so the FastAPI event loop
	stays free to serve health checks, polling, and inbound chat requests
	while a generation is in flight.
	"""

	def __init__(self):
		self.shopping_service = get_shopping_service()
		self.ranking_service = ProductRankingService()
		self.gemini_client = get_gemini_client()
		self.openai_client = get_openai_client()

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

			results_arr: List[Dict[str, Any]] = []
			ratings_arr: List[int] = []

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

			await aexec(db.outfit_items.update_search_results, item_id, results_arr)

			if config.PRODUCT_RANKING_ENABLED:
				ranked_results, ratings = await self.ranking_service.rank_results(
					user_data=user_data,
					item_context={"keywords": keywords, "item_id": item_id},
					results=unranked_results,
					outfit_row=outfit_row,
				)
				results_arr = ranked_results
				ratings_arr = ratings

			rank_time = time.time() - start_time - shop_time
			await aexec(db.outfit_items.update_search_results, item_id, results_arr)

			logger.info(
				f"🔍 {keywords}\n"
				f"  🛒 {shop_time:.1f}s | {unranked_results_length} -> {filtered_results_length} res\n"
				f"  🏆 {rank_time:.1f}s | {ratings_arr}"
			)

		except asyncio.CancelledError:
			raise
		except Exception as e:
			logger.error(f"Failed to process item with keywords '{keywords}': {e}")

	async def _process_items_with_limit(
		self,
		*,
		items: List[Dict[str, Any]],
		user_data: Dict[str, Any],
		outfit_row: Dict[str, Any],
	) -> Dict[str, Any]:
		"""Search/rank outfit items with bounded concurrency."""
		limit = max(1, int(getattr(config, "ITEM_PROCESSING_CONCURRENCY", 1)))
		semaphore = asyncio.Semaphore(limit)

		async def run_item(item: Dict[str, Any]) -> None:
			item_id = item.get("id")
			keywords = (item.get("keywords") or "").strip()
			if not item_id or not keywords:
				return
			async with semaphore:
				await self._process_single_item(
					item_id=item_id,
					keywords=keywords,
					user_data=user_data,
					outfit_row=outfit_row,
				)

		tasks = [asyncio.create_task(run_item(item)) for item in items]
		if not tasks:
			return {"success": True, "items_processed": 0}

		results = await asyncio.gather(*tasks, return_exceptions=True)
		errors = sum(1 for result in results if isinstance(result, Exception))
		return {
			"success": errors == 0,
			"items_processed": len(tasks),
			"errors": errors,
		}

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
		"""Persist a single outfit and kick off image rendering + product search."""
		try:
			should_cache = False
			if force_cached:
				should_cache = True
			elif double_batch:
				# Keep the first generated frame visible and hold the rest in reserve.
				should_cache = outfit_count > config.NUM_OUTFITS_IN_GRID

			outfit_id = await aexec(
				db.outfits.create,
				name=outfit.get("name"),
				thread_id=thread_id,
				is_cached=should_cache,
			)

			for item in outfit.get("items") or []:
				await aexec(
					db.outfit_items.create,
					outfit_id=outfit_id,
					type=item.get("type"),
					keywords=item.get("keywords"),
				)

			# Render the flatlay before product search so image generation
			# overlaps with the slower search/ranking stage.
			register_callback(outfit, outfit_id)

			spawn(
				self.search_and_rank_for_outfit(outfit_id=outfit_id),
				name=f"search-rank:{(thread_id or 'unknown')[:6]}:{outfit_count}",
				key=f"search-rank:{outfit_id}",
			)

		except asyncio.CancelledError:
			raise
		except Exception as e:
			logger.error(f"Failed to process outfit: {e}")

	async def search_and_rank_for_outfit(self, *, outfit_id: str) -> Dict[str, Any]:
		async with _search_rank_outfit_semaphore:
			return await self._search_and_rank_for_outfit(outfit_id=outfit_id)

	async def _search_and_rank_for_outfit(self, *, outfit_id: str) -> Dict[str, Any]:
		outfit_row = await aexec(db.outfits.get, outfit_id)
		if not outfit_row:
			return {"success": False, "message": "Outfit not found"}

		thread_id: Optional[str] = outfit_row.get("thread_id")
		user_data: Dict[str, Any] = {}

		try:
			if thread_id:
				thread = await aexec(db.threads.get, thread_id)
				user_id = thread.get("user_id") if thread else None
				if user_id:
					user_data = await aexec(db.users.get_relevant_context, user_id) or {}
		except Exception:
			user_data = {}

		items = await aexec(db.outfit_items.get_by_outfit, outfit_id)
		if not items:
			return {"success": True, "items_processed": 0}

		return await self._process_items_with_limit(
			items=items,
			user_data=user_data,
			outfit_row=outfit_row,
		)

	async def _search_and_rank_item_ids(
		self,
		*,
		outfit_id: str,
		item_ids: List[str],
		user_data: Dict[str, Any],
	) -> Dict[str, Any]:
		outfit_row = await aexec(db.outfits.get, outfit_id)
		if not outfit_row:
			return {"success": False, "message": "Outfit not found"}

		item_id_set = set(item_ids)
		all_items = await aexec(db.outfit_items.get_by_outfit, outfit_id)
		items = [item for item in all_items if item.get("id") in item_id_set]

		return await self._process_items_with_limit(
			items=items,
			user_data=user_data,
			outfit_row=outfit_row,
		)

	async def remix_outfit(self, *, outfit_id: str, feedback: str) -> Dict[str, Any]:
		"""Kick off a remix and return the new outfit id immediately.

		The expensive work (LLM remix plan, item creation, search & rank,
		image generation) is moved to a background task so the client can
		render a loading slide for the new outfit right away. The remix
		slot is wedged in front of any cached upcoming outfit by
		assigning `outfit_order = max(visible) + 1`, leaving the cache
		untouched.
		"""
		feedback = (feedback or "").strip()
		if not feedback:
			return {"success": False, "message": "Feedback is required"}

		existing_outfit = await aexec(db.outfits.get, outfit_id)
		if not existing_outfit:
			return {"success": False, "message": "Outfit not found"}

		thread_id: Optional[str] = existing_outfit.get("thread_id")
		if not thread_id:
			return {"success": False, "message": "Outfit thread not found"}

		next_order = await aexec(
			db.outfits.get_max_outfit_order,
			thread_id,
			only_visible=True,
		) + 1

		new_outfit_id = await aexec(
			db.outfits.create,
			thread_id=thread_id,
			name=f"{existing_outfit.get('name') or 'Outfit'} Remix",
			is_cached=False,
			outfit_order=next_order,
		)
		if not new_outfit_id:
			return {"success": False, "message": "Failed to create remixed outfit"}

		spawn(
			self._fill_remix_outfit(
				new_outfit_id=new_outfit_id,
				existing_outfit=existing_outfit,
				thread_id=thread_id,
				feedback=feedback,
			),
			name=f"remix-fill:{thread_id[:6]}",
			key=f"remix-fill:{new_outfit_id}",
		)

		return {
			"success": True,
			"thread_id": thread_id,
			"outfit_id": new_outfit_id,
		}

	async def _fill_remix_outfit(
		self,
		*,
		new_outfit_id: str,
		existing_outfit: Dict[str, Any],
		thread_id: str,
		feedback: str,
	) -> None:
		"""Background worker: compute the remix plan and populate the new outfit."""
		try:
			thread = await aexec(db.threads.get, thread_id)
			user_id = thread.get("user_id") if thread else None
			user_data = (
				await aexec(db.users.get_relevant_context, user_id) if user_id else {}
			)
			existing_items = await aexec(
				db.outfit_items.get_by_outfit, existing_outfit.get("id")
			)
			items_by_id = {
				item.get("id"): item for item in existing_items if item.get("id")
			}

			remix = await self.openai_client.generate_remix_outfit_flow(
				user_data=user_data or {},
				existing_outfit=existing_outfit,
				existing_items=existing_items,
				feedback=feedback,
			)

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

				new_item_id = await aexec(
					db.outfit_items.create,
					outfit_id=new_outfit_id,
					type=item_type,
					keywords=keywords,
				)
				if not new_item_id:
					continue

				if should_reuse:
					search_results = source_item.get("search_results") or []
					if search_results:
						await aexec(
							db.outfit_items.update_search_results,
							new_item_id,
							search_results,
						)
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
					key=f"remix-search:{new_outfit_id}",
				)

			if user_id:
				self.gemini_client.launch_flatlay_task(
					outfits=[image_outfit],
					outfit_ids=[new_outfit_id],
					user_id=user_id,
					thread_id=thread_id,
				)
		except asyncio.CancelledError:
			raise
		except Exception as e:
			logger.error(f"Failed to fill remix outfit {new_outfit_id[:6]}: {e}")

	async def generate_outfits_for_thread(self, thread_id: str) -> Dict[str, Any]:
		"""Generate outfits for a thread with smart caching logic."""
		try:
			thread = await aexec(db.threads.get, thread_id)
			if not thread:
				return {"success": False, "error": "Thread not found"}

			user_id = thread.get("user_id")
			user_data = await aexec(db.users.get_relevant_context, user_id) if user_id else {}
			conversation_history = await aexec(db.threads.get_conversation_history, thread_id)
			outfit_history = await aexec(db.outfits.get_thread_outfit_history, thread_id)

			await self._generate_outfits_batch(
				thread_id, user_id, user_data, conversation_history, outfit_history, double_batch=True,
			)

			return {"success": True, "thread_id": thread_id}

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
		async with _outfit_generation_semaphore:
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
						thread_id=thread_id,
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
		thread = await aexec(db.threads.get, thread_id)
		if not thread:
			return {"success": False, "message": "Thread not found"}

		cached_outfit = await aexec(db.outfits.get_next_cached_for_thread, thread_id)
		if not cached_outfit:
			return {
				"success": True,
				"thread_id": thread_id,
				"outfit_id": None,
				"revealed": False,
			}

		# Reveal the cached outfit, but place it *after* every existing
		# visible outfit (e.g. any in-flight remix). Without this bump, the
		# cached row's older `created_at` could push it above a remix that
		# was injected just before it.
		next_order = await aexec(
			db.outfits.get_max_outfit_order,
			thread_id,
			only_visible=True,
		) + 1
		await aexec(db.outfits.update_outfit_order, cached_outfit["id"], next_order)
		await aexec(db.outfits.update_is_cached, cached_outfit["id"], False)

		user_id = thread.get("user_id")
		user_data = await aexec(db.users.get_relevant_context, user_id) if user_id else {}
		conversation_history = await aexec(db.threads.get_conversation_history, thread_id)
		outfit_history = await aexec(db.outfits.get_thread_outfit_history, thread_id)

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
			key=f"refill-cache:{thread_id}",
		)

		return {
			"success": True,
			"thread_id": thread_id,
			"outfit_id": cached_outfit.get("id"),
			"revealed": True,
		}


_service: Optional[OutfitGenerationService] = None


def get_outfit_generation_service() -> OutfitGenerationService:
	global _service
	if _service is None:
		_service = OutfitGenerationService()
	return _service
