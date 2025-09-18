import httpx
import os
from typing import Dict, Any, List, Optional, Tuple
import _config
import logging
from utils.search_client_utils import (
    build_query,
    cap_results,
    create_async_httpx_client,
    create_semaphore,
    filter_blocked_sources,
    filter_by_gender,
    filter_price_min_max,
    filter_by_rating,
)

logger = logging.getLogger(__name__)


class SerperShoppingClient:
    """Pure Serper.dev shopping client implementation."""
    
    def __init__(self, max_concurrency: int = None):
        self.api_key = os.getenv("SERPER_API_KEY")
        self.base_url = "https://google.serper.dev/shopping"
        max_conc = max_concurrency or _config.SERPER_MAX_CONCURRENCY
        self._client: Optional[httpx.AsyncClient] = create_async_httpx_client(timeout_seconds=15.0)
        self._sem = create_semaphore(max_conc)
    
    async def aclose(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def search_item(
            self, 
            keywords: str, 
            user_gender: str, 
            min_price: int | None = _config.SHOPPING_MIN_PRICE, 
            max_price: int | None = _config.SHOPPING_MAX_PRICE,
            ) -> Tuple[List[Dict[str, Any]], int]:
        """Search for a single item using keywords, returns raw search results."""
        async with self._sem:
            if not self.api_key:
                raise ValueError("SERPER_API_KEY is required")
            
            query = build_query(keywords)

            # Request the configured number from Serper
            num_to_request = max(1, _config.SHOPPING_RESULTS_TO_FETCH)

            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "q": query,
                "num": num_to_request,
                "gl": "us",
                "engine": "shopping",
                "location": "New York, New York, United States",
            }
            
            try:
                response = await self._client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                
                # Return raw shopping results - filter ALL results first, then cap for ranking
                items = data.get("shopping", [])

                unfiltered_results_length = len(items)
                
                # Apply source filtering to ALL results
                items = filter_blocked_sources(items, _config.BLOCKED_SOURCES)
                items = filter_by_gender(items, user_gender)
                items = filter_price_min_max(items, min_price, max_price)

                items_before_rating_filter = items
                items = filter_by_rating(items)
                if len(items) < 8:
                    items = items_before_rating_filter

                # Then cap to what we intend to rank
                filtered_results_length = len(items)
                cap = max(_config.SHOPPING_RESULTS_TO_RANK, 1)
                items = cap_results(items, cap)

                return items, unfiltered_results_length, filtered_results_length
                
            except Exception as e:
                logger.error("❌ Serper search failed for '%s'", keywords)
                raise e  
            
            