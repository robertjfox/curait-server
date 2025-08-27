import logging
import asyncio
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
        
        async with self._ranking_semaphore:
            try:
                top_k = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RETURN", 10)))
                cap = max(1, int(getattr(_config, "SHOPPING_RESULTS_TO_RANK", 20)))
                head = (results or [])[:cap]

                products_with_images = [r for r in head if r.get("imageUrl")]
                if not products_with_images:
                    logger.warning(f"No products with images found for grid creation. Total results: {len(head)}, Results with images: 0")
                    raise ValueError("No products with images found for ranking")
                
                # Use the actual number of products with images for consistency
                n = len(products_with_images)
                
                try:
                    # Extract keywords from item_context for the header
                    ranking_keywords = item_context.get("keywords") if item_context else None
                    img_bytes, public_url, filename = await create_product_grid_and_upload(
                        products_with_images,
                        ranking_keywords=ranking_keywords
                    )
                    grid_data_uri = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode('ascii')}"
                except Exception as grid_err:
                    logger.error(f"🖼️ GRID CREATION FAILED: {grid_err}")
                    raise grid_err

                try:
                    ratings = await self.openai_client.rank_products_flow(
                        user_data=user_data,    
                        item_context=item_context,
                        num_results=n,
                        grid_image_data_uri=grid_data_uri,
                    )
                except Exception as ranking_err:
                    logger.warning(f"Failed to rank products: {ranking_err}")
                    raise ranking_err

                # Rank and sort results using products_with_images instead of head
                sorted_indices = sorted(range(n), key=lambda i: (-ratings[i], i))
                ranked_all: List[Dict[str, Any]] = []
                for idx in sorted_indices:
                    product = products_with_images[idx].copy()
                    product["ranking"] = ratings[idx]
                    product["original_index"] = idx
                    ranked_all.append(product)
                final_ranked = ranked_all[:top_k]

                return final_ranked, ratings

            except Exception as e:
                if isinstance(e, asyncio.TimeoutError):
                    logger.warning(f"Product ranking timed out after {_config.RANKING_TIMEOUT}s")
                else:
                    error_type = type(e).__name__
                    logger.warning(f"Product ranking failed ({error_type}): {str(e)[:100]}...")
                raise e