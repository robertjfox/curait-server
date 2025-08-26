import logging
import asyncio
import time
from typing import Any, Dict, List

from clients.openai_client import get_openai_client
import _config
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
        
        grid_start_time = None
        
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
                
                grid_start_time = time.time()
                try:
                    # Extract keywords from item_context for the header
                    ranking_keywords = item_context.get("keywords") if item_context else None
                    img_bytes, public_url, filename = await create_product_grid_and_upload(
                        products_with_images,
                        ranking_keywords=ranking_keywords
                    )
                    grid_data_uri = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('ascii')}"
                except Exception as grid_err:
                    logger.error(f"🖼️ GRID CREATION FAILED - Returning first {top_k} results unranked: {grid_err}")
                    return head[:top_k]

                grid_end_time = time.time()
                ai_start_time = time.time()
                
                try:
                    ratings = await self.openai_client.rank_products_flow(
                        user_data=user_data,    
                        item_context=item_context,
                        num_results=n,
                        grid_image_data_uri=grid_data_uri,
                        thread_id=thread_id,
                        timeout=getattr(_config, "RANKING_TIMEOUT", None),
                    )
                except Exception as ranking_err:
                    logger.warning(f"Failed to rank products: {ranking_err}")
                    return head[:top_k]

                # Rank and sort results
                sorted_indices = sorted(range(n), key=lambda i: (-ratings[i], i))
                ranked_all: List[Dict[str, Any]] = []
                for idx in sorted_indices:
                    product = head[idx].copy()
                    product["ranking"] = ratings[idx]
                    product["original_index"] = idx
                    ranked_all.append(product)
                final_ranked = ranked_all[:top_k]



                # Log timing information with correct measurements
                grid_time = grid_end_time - grid_start_time
                ai_time = time.time() - ai_start_time   
                logger.info(f"Grid creation: {grid_time:.2f}s, AI: {ai_time:.2f}s")

                return final_ranked

            except Exception as e:
                if isinstance(e, asyncio.TimeoutError):
                    logger.warning(f"Product ranking timed out after {_config.RANKING_TIMEOUT}s, returning unranked results")
                else:
                    error_type = type(e).__name__
                    logger.warning(f"Product ranking failed ({error_type}): {str(e)[:100]}...")
                top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
                return (results or [])[:top_k]