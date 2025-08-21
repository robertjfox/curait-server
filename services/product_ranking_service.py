import logging
import asyncio
import time
from typing import Any, Dict, List

from clients.openai_client import get_openai_client
import _config
from utils.image_processing.background_removal import SupabaseBackgroundProcessor
from utils.image_processing.create_image_grid import create_product_grid_and_upload
import base64

logger = logging.getLogger(__name__)


class ProductRankingService:
    def __init__(self):
        self.openai_client = get_openai_client()
        self._ranking_semaphore = asyncio.Semaphore(_config.RANKING_BATCH_SIZE)

    async def rank_results(
        self,
        user_data: Dict[str, Any],
        item_context: Dict[str, Any],
        results: List[Dict[str, Any]],
        thread_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Rank products using image-only AI analysis by creating a product grid, asking the
        model for per-item ratings (1–10), and returning the top-K items where
        K = SHOPPING_RESULTS_TO_RETURN. On any failure, return the first K results
        unchanged. Also applies background removal to the top ranked product.
        """
        start_time = time.time()
        keywords = item_context.get("keywords", "unknown")
        logger.info(f"[ 📊 RANK ] Starting ranking for '{keywords}' with {len(results)} results")
        
        async with self._ranking_semaphore:
            try:
                top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
                cap = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RANK", 20)))
                head = (results or [])[:cap]
                n = len(head)

                products_with_images = [r for r in head if r.get("imageUrl")]
                if not products_with_images:
                    logger.warning("No products with images found for grid creation")
                    return head[:top_k]

                # Create product grid image
                grid_start = time.time()
                try:
                    img_bytes, public_url, filename = await create_product_grid_and_upload(products_with_images)
                    grid_data_uri = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('ascii')}"
                    grid_time = time.time() - grid_start
                    logger.info(f"[ 📊 RANK ] Grid created in {grid_time:.1f}s for '{keywords}'")
                except Exception as grid_err:
                    logger.error(f"🖼️ GRID CREATION FAILED - Returning first {top_k} results unranked: {grid_err}")
                    return head[:top_k]

                # Call centralized ranking flow
                ai_start = time.time()
                try:
                    ratings = await self.openai_client.rank_products_flow(
                        user_data=user_data,    
                        item_context=item_context,
                        num_results=n,
                        grid_image_data_uri=grid_data_uri,
                        thread_id=thread_id,
                        timeout=getattr(_config, "RANKING_TIMEOUT", None),
                    )
                    ai_time = time.time() - ai_start
                    logger.info(f"[ 📊 RANK ] AI ranking completed in {ai_time:.1f}s for '{keywords}'")
                except Exception as ranking_err:
                    logger.warning(f"Failed to rank products: {ranking_err}")
                    return head[:top_k]

                # Rank and sort results
                sort_start = time.time()
                sorted_indices = sorted(range(n), key=lambda i: (-ratings[i], i))
                ranked_all: List[Dict[str, Any]] = []
                for idx in sorted_indices:
                    product = head[idx].copy()
                    product["ranking"] = ratings[idx]
                    ranked_all.append(product)
                final_ranked = ranked_all[:top_k]

                # Optional background removal on top product
                if final_ranked and getattr(_config, "BACKGROUND_REMOVAL_ENABLED", False) and final_ranked[0].get("imageUrl"):
                    async with SupabaseBackgroundProcessor() as processor:
                        final_ranked[0]["imageUrl"] = await processor.process_image(final_ranked[0]["imageUrl"])

                # Final timing summary
                total_time = time.time() - start_time
                sort_time = time.time() - sort_start
                logger.info(f"[ 📊 RANK ] ✅ Completed ranking for '{keywords}' in {total_time:.1f}s total (sort: {sort_time:.1f}s)")
                
                return final_ranked

            except Exception as e:
                if isinstance(e, asyncio.TimeoutError):
                    logger.warning(f"Product ranking timed out after {_config.RANKING_TIMEOUT}s, returning unranked results")
                else:
                    error_type = type(e).__name__
                    logger.warning(f"Product ranking failed ({error_type}): {str(e)[:100]}...")
                top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
                return (results or [])[:top_k]