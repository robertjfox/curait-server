import httpx
import os
import asyncio
from typing import Dict, Any, List, Optional
import _config
import logging
import time
from utils.search_client_utils import (
    build_query,
    cap_results,
    create_async_httpx_client,
    create_semaphore,
    filter_blocked_sources,
    filter_by_gender,
    # filter_price_min_max,
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
    
    async def search_item(self, keywords: str, user_gender: str, thread_id: str = None) -> List[Dict[str, Any]]:
        """Search for a single item using keywords, returns raw search results."""
        async with self._sem:
            if not self.api_key:
                raise ValueError("SERPER_API_KEY is required")
            
            query = build_query(keywords)

            # add price min max to the end of the query like $100 - $200
            # query = f"{query} ${_config.SHOPPING_MIN_PRICE} - ${_config.SHOPPING_MAX_PRICE}"

            # add "new" to the end of the query
            query = f"{query} new"

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
                start_time = time.time()

                response = await self._client.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                
                # Return raw shopping results - filter ALL results first, then cap for ranking
                shopping_results_full = data.get("shopping", [])
                
                # Apply source filtering to ALL results
                shopping_results_filtered = filter_blocked_sources(shopping_results_full, _config.BLOCKED_SOURCES)
                shopping_results_filtered = filter_by_gender(shopping_results_filtered, user_gender)
                # shopping_results_filtered = filter_price_min_max(shopping_results_filtered, _config.SHOPPING_MIN_PRICE, _config.SHOPPING_MAX_PRICE)

                # Then cap to what we intend to rank
                cap = max(_config.SHOPPING_RESULTS_TO_RANK, 1)
                shopping_results = cap_results(shopping_results_filtered, cap)

                duration = time.time() - start_time
                # Individual search logging removed - see batch log in thread_service

                return shopping_results
                
            except Exception as e:
                logger.error("❌ Serper search failed for '%s'", keywords)
                raise e  
            
            