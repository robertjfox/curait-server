import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple
import logging
import httpx
import random

import _config
from utils.search_client_utils import (
    build_query,
    cap_results,
    create_async_httpx_client,
    create_semaphore,
    normalize_serpapi_results,
    filter_blocked_sources,
    filter_by_gender,
    filter_by_min_price,
)

logger = logging.getLogger(__name__)

class SerpApiShoppingClient:
    def __init__(self, max_concurrency: int | None = None):
        self.api_key = os.getenv("SERPAPI_API_KEY")
        self.base_url = "https://serpapi.com/search.json"
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

        """Search for a single item using keywords, returns normalized shopping results"""
        async with self._sem:
            assert self._client is not None, "SerpApiShoppingClient is closed"

            # Build query and payload
            query = build_query(keywords)

            query += " sponsored"

            logger.info(f"Query: {query}")

            num_to_fetch = _config.SHOPPING_RESULTS_TO_FETCH

            params = {
                "api_key": self.api_key,
                "engine": "google_shopping_light",
                "q": query,
                "gl": "us",
                "hl": "en",
                "location": "New York, New York, United States",
                "num": num_to_fetch,
                # "json_restrictor": "shopping_results[].{title, product_link, price, source, thumbnail, rating, reviews}"
            }

            max_attempts = 2
            base_delay = 0.5

            for attempt in range(1, max_attempts + 1):

                try:
                    resp = await self._client.get(self.base_url, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                    items = data.get("shopping_results", []) or data.get("inline_shopping_results", [])
                    unfiltered_results_length = len(items)

                    items = normalize_serpapi_results(items)

                    # Hard, deterministic filters (always applied):
                    #   1. Blocked sources (eBay / aliexpress / etc.)
                    #   2. Minimum price floor (SHOPPING_MIN_PRICE)
                    items = filter_blocked_sources(items, _config.BLOCKED_SOURCES)
                    items = filter_by_min_price(items, _config.SHOPPING_MIN_PRICE)
                    items = filter_by_gender(items, user_gender)

                    filtered_results_length = len(items)

                    # Then cap to what we intend to rank
                    items = cap_results(items, _config.SHOPPING_RESULTS_TO_RANK)

                    return items, unfiltered_results_length, filtered_results_length

                except Exception as e:
                    if attempt < max_attempts:
                        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                        logger.warning("SerpApi attempt %d/%d failed for '%s': %s; retrying in %.2fs", attempt, max_attempts, keywords, str(e), delay)
                        await asyncio.sleep(delay)
                        continue
                    logger.error("❌ SerpApi search failed for '%s' after %d attempts", keywords, max_attempts)
                    raise e 