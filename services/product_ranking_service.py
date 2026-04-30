import logging
import asyncio
from typing import Any, Dict, List, Tuple
import time
from uuid import uuid4
import base64

from clients.openai_client import get_openai_client
from clients.supabase_client import get_supabase_client
from interfaces._retry import with_retry
import _config
from utils.image_processing.create_image_grid import create_product_grid

logger = logging.getLogger(__name__)

_ranking_semaphore = asyncio.Semaphore(max(1, int(_config.RANKING_BATCH_SIZE)))


class ProductRankingService:
	def __init__(self):
		self.openai_client = get_openai_client()

	async def _upload_ranking_grid(
		self,
		*,
		image_bytes: bytes,
		outfit_row: Dict[str, Any],
		item_context: Dict[str, Any],
	) -> str | None:
		"""Persist ranking grid images for audit/debugging without blocking ranking.

		Supabase storage is sync; we run the upload in a worker thread so
		the event loop is not held while the bytes are pushed to Supabase.
		"""
		if not _config.PRODUCT_RANKING_GRID_UPLOAD_ENABLED:
			return None

		def _do_upload() -> str | None:
			try:
				outfit_id = outfit_row.get("id") or "unknown-outfit"
				item_id = item_context.get("item_id") or "unknown-item"
				filename = f"{outfit_id}/{item_id}/{int(time.time() * 1000)}-{uuid4().hex}.jpg"
				bucket = "product-ranking-grids"
				def _upload() -> str:
					storage = get_supabase_client().storage.from_(bucket)
					storage.upload(filename, image_bytes, {"content-type": "image/jpeg"})
					return storage.get_public_url(filename)
				return with_retry(_upload)
			except Exception as exc:
				logger.warning("Failed to upload product ranking grid: %s", exc)
				return None

		return await asyncio.to_thread(_do_upload)

	async def rank_results(
		self,
		user_data: Dict[str, Any],
		item_context: Dict[str, Any],
		results: List[Dict[str, Any]],
		outfit_row: Dict[str, Any],
	) -> Tuple[List[Dict[str, Any]], List[int]]:
		async with _ranking_semaphore:
			try:
				start_time = time.time()

				top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
				cap = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RANK", 20)))
				head = (results or [])[:cap]

				products_with_images = [r for r in head if r.get("imageUrl")]

				if not products_with_images:
					logger.warning(
						"No products with images found for grid creation. Total results: %d, with images: 0",
						len(head),
					)
					fallback_results = head[:top_k]
					fallback_ratings = [5] * len(fallback_results)
					return fallback_results, fallback_ratings

				grid_cap = max(1, int(getattr(_config, "RANKING_IMAGE_MAX_PRODUCTS", cap)))
				ranking_candidates = products_with_images[:grid_cap]
				n = len(ranking_candidates)

				try:
					ranking_keywords = item_context.get("keywords") if item_context else None
					img_bytes = await create_product_grid(
						ranking_candidates,
						ranking_keywords=ranking_keywords,
					)
					ranking_grid_url = await self._upload_ranking_grid(
						image_bytes=img_bytes,
						outfit_row=outfit_row,
						item_context=item_context,
					)
					grid_data_uri = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('ascii')}"

				except Exception as grid_err:
					logger.error(f"🖼️ GRID CREATION FAILED: {grid_err}")
					fallback_results = ranking_candidates[:top_k]
					fallback_ratings = [5] * len(fallback_results)
					return fallback_results, fallback_ratings

				try:
					ratings = await asyncio.wait_for(
						self.openai_client.rank_products_flow(
							user_data=user_data,
							item_context=item_context,
							products=ranking_candidates,
							num_results=n,
							grid_image_data_uri=grid_data_uri,
							outfit_row=outfit_row,
						),
						timeout=float(getattr(_config, "RANKING_TIMEOUT", 60)),
					)

				except Exception as ranking_err:
					logger.warning(f"Failed to rank products: {ranking_err}")
					fallback_results = [
						{**product, "ranking_grid_url": ranking_grid_url}
						for product in ranking_candidates[:top_k]
					]
					fallback_ratings = [5] * len(fallback_results)
					return fallback_results, fallback_ratings

				# Sort high-scoring products first; keep low-scoring as fallbacks
				# so a bad model pass never erases the visible row.
				sorted_indices = sorted(range(n), key=lambda i: (-ratings[i], i))
				ranked_all: List[Dict[str, Any]] = []
				for idx in sorted_indices:
					product = ranking_candidates[idx].copy()
					product["ranking"] = ratings[idx]
					product["original_index"] = idx
					product["ranking_grid_url"] = ranking_grid_url
					ranked_all.append(product)
				final_ranked = ranked_all[:top_k]

				return final_ranked, ratings

			except Exception as e:
				if isinstance(e, asyncio.TimeoutError):
					logger.warning(f"Product ranking timed out after {_config.RANKING_TIMEOUT}s")
				else:
					error_type = type(e).__name__
					logger.warning(f"Product ranking failed ({error_type}): {str(e)[:100]}...")

				top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
				fallback_results = (results or [])[:top_k]
				fallback_ratings = [5] * len(fallback_results)
				return fallback_results, fallback_ratings
