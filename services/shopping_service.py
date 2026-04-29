import os
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from clients.shopping.serper_client import SerperShoppingClient
from clients.shopping.serpapi_client import SerpApiShoppingClient
import _config as config

logger = logging.getLogger(__name__)


class ShoppingService:
    """Shopping service that directly uses serper or serpapi clients based on SEARCH_PROVIDER env var."""
    
    def __init__(self, max_concurrency: Optional[int] = None):
        self._provider = os.getenv("SEARCH_PROVIDER", "serper").lower().strip()
        self._client = None
        self._max_concurrency = max_concurrency
        
        # Initialize the appropriate client
        if self._provider == "serpapi":
            try:
                self._client = SerpApiShoppingClient(max_concurrency=max_concurrency)
            except ImportError:
                logger.warning("SerpApi client not available, falling back to Serper")
                self._provider = "serper"
        
        if self._provider == "serper" or self._client is None:
            self._client = SerperShoppingClient(max_concurrency=max_concurrency)
    
    async def search_for_keywords(
        self, 
        keywords: str, 
        user_data: Dict[str, Any], 
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """Search for products based on keywords."""
        try:
            results, unfiltered_results_length, filtered_results_length = await asyncio.wait_for(
                self._client.search_item(
                    keywords=keywords,
                    user_gender=user_data.get("gender"),
                ),
                timeout=config.SHOPPING_SEARCH_TIMEOUT,
            )

            return results or [], unfiltered_results_length, filtered_results_length
        except asyncio.TimeoutError:
            logger.error(
                "Shopping search timed out after %.1fs for keywords '%s'",
                config.SHOPPING_SEARCH_TIMEOUT,
                keywords,
            )
            return [], 0, 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                "Shopping search failed for keywords '%s' (%s): %s",
                keywords,
                type(e).__name__,
                e,
            )
            return [], 0, 0
    
    async def aclose(self):
        """Close the underlying client."""
        if self._client:
            await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose() 