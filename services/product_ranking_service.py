import logging
import asyncio
from typing import Any, Dict, List, Tuple
import time
from uuid import uuid4

from clients.openai_client import get_openai_client
from clients.supabase_client import get_supabase_client
import _config
from utils.image_processing.create_image_grid import create_product_grid
import base64

logger = logging.getLogger(__name__)


class ProductRankingService:
    def __init__(self):
        self.openai_client = get_openai_client()
        self.supabase = get_supabase_client()
        self._ranking_semaphore = asyncio.Semaphore(_config.RANKING_BATCH_SIZE)

    def _upload_ranking_grid(
        self,
        *,
        image_bytes: bytes,
        outfit_row: Dict[str, Any],
        item_context: Dict[str, Any],
    ) -> str | None:
        """Persist ranking grid images for audit/debugging without blocking ranking."""
        if not _config.PRODUCT_RANKING_GRID_UPLOAD_ENABLED:
            return None

        try:
            outfit_id = outfit_row.get("id") or "unknown-outfit"
            item_id = item_context.get("item_id") or "unknown-item"
            filename = f"{outfit_id}/{item_id}/{int(time.time() * 1000)}-{uuid4().hex}.jpg"
            bucket = "product-ranking-grids"
            self.supabase.storage.from_(bucket).upload(
                filename,
                image_bytes,
                {"content-type": "image/jpeg"},
            )
            return self.supabase.storage.from_(bucket).get_public_url(filename)
        except Exception as exc:
            logger.warning("Failed to upload product ranking grid: %s", exc)
            return None

    async def rank_results(
        self,
        user_data: Dict[str, Any],
        item_context: Dict[str, Any],
        results: List[Dict[str, Any]],
        outfit_row: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[int]]:
        
        async with self._ranking_semaphore:
            try:

                start_time = time.time()

                top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
                cap = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RANK", 20)))
                head = (results or [])[:cap]

                products_with_images = [r for r in head if r.get("imageUrl")]

                if not products_with_images:
                    logger.warning(f"No products with images found for grid creation. Total results: {len(head)}, Results with images: 0")
                    # Fallback: return first K results unchanged with default ratings
                    fallback_results = head[:top_k]
                    fallback_ratings = [5] * len(fallback_results)  # Default rating of 5
                    return fallback_results, fallback_ratings
                
                # The grid, prompt metadata, expected ratings, and ranked products
                # must all refer to this exact slice.
                grid_cap = max(1, int(getattr(_config, "RANKING_IMAGE_MAX_PRODUCTS", cap)))
                ranking_candidates = products_with_images[:grid_cap]
                n = len(ranking_candidates)
                
                try:
                    # Extract keywords from item_context for the header
                    ranking_keywords = item_context.get("keywords") if item_context else None
                    img_bytes = await create_product_grid(
                        ranking_candidates,
                        ranking_keywords=ranking_keywords,
                    )
                    ranking_grid_url = self._upload_ranking_grid(
                        image_bytes=img_bytes,
                        outfit_row=outfit_row,
                        item_context=item_context,
                    )
                    grid_data_uri = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('ascii')}"

                except Exception as grid_err:
                    logger.error(f"🖼️ GRID CREATION FAILED: {grid_err}")
                    # Fallback: return products with images unchanged with default ratings
                    fallback_results = ranking_candidates[:top_k]
                    fallback_ratings = [5] * len(fallback_results)
                    return fallback_results, fallback_ratings

                try:
                    ratings = await self.openai_client.rank_products_flow(
                        user_data=user_data,    
                        item_context=item_context,
                        products=ranking_candidates,
                        num_results=n,
                        grid_image_data_uri=grid_data_uri,
                        outfit_row=outfit_row,
                    )

                except Exception as ranking_err:
                    logger.warning(f"Failed to rank products: {ranking_err}")
                    # Fallback: return products with images unchanged with default ratings
                    fallback_results = [
                        {
                            **product,
                            "ranking_grid_url": ranking_grid_url,
                        }
                        for product in ranking_candidates[:top_k]
                    ]
                    fallback_ratings = [5] * len(fallback_results)
                    return fallback_results, fallback_ratings

                # Rank high-scoring products first. Keep low-scoring products as
                # fallbacks so a bad model pass never erases the visible row.
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
                
                # Fallback: return first K results unchanged with default ratings
                top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
                fallback_results = (results or [])[:top_k]
                fallback_ratings = [5] * len(fallback_results)
                return fallback_results, fallback_ratings