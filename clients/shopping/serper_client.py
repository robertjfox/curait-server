import httpx
import os
import asyncio
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
    filter_by_min_price,
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
            ) -> Tuple[List[Dict[str, Any]], int, int]:
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
            
            max_attempts = 2
            for attempt in range(1, max_attempts + 1):
                try:
                    if attempt > 1:
                        logger.info("Serper retry %d/%d: %s", attempt, max_attempts, query)
                    response = await self._client.post(
                        self.base_url,
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        "❌ Serper search failed for '%s' (query='%s', attempt=%d/%d, %s): %s",
                        keywords,
                        query,
                        attempt,
                        max_attempts,
                        type(e).__name__,
                        e,
                    )
                    if attempt >= max_attempts:
                        raise
                    await asyncio.sleep(0.25 * attempt)

            # Return raw shopping results - filter ALL results first, then cap for ranking
            items = data.get("shopping", [])

            unfiltered_results_length = len(items)

            # Hard, deterministic filters (always applied, no safety net):
            #   1. Blocked sources (eBay / aliexpress / etc.)
            #   2. Minimum price floor (SHOPPING_MIN_PRICE)
            items = filter_blocked_sources(items, _config.BLOCKED_SOURCES)
            items = filter_by_min_price(items, _config.SHOPPING_MIN_PRICE)

            # Gender filter is best-effort: keep unfiltered if it would
            # leave us with too few products to rank meaningfully.
            filtered_items = filter_by_gender(items, user_gender)
            if len(filtered_items) >= 8:
                items = filtered_items

            # Then cap to what we intend to rank
            filtered_results_length = len(items)
            cap = max(_config.SHOPPING_RESULTS_TO_RANK, 1)
            items = cap_results(items, cap)

            return items, unfiltered_results_length, filtered_results_length
            
            