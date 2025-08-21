import os
import asyncio
from typing import Any, Dict, List, Optional
import logging
import time
import httpx
import json
import random
from pathlib import Path

import _config
from utils.search_client_utils import (
    build_query,
    cap_results, 
    create_async_httpx_client,
    create_semaphore,
    normalize_serpapi_results,
    filter_blocked_sources,
    filter_by_gender,
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

    async def search_item(self, keywords: str, user_gender: str, thread_id: str | None = None) -> List[Dict[str, Any]]:
        """Search for a single item using keywords, returns normalized shopping results"""
        async with self._sem:
            assert self._client is not None, "SerpApiShoppingClient is closed"

            # Build query and payload
            query = build_query(keywords)
            num_to_fetch = max(_config.SHOPPING_RESULTS_TO_FETCH, 1)

            params = {
                "api_key": self.api_key,
                "engine": "google_shopping",
                "q": query,
                "gl": "us",
                "hl": "en",
                "location": "New York, New York, United States",
                "num": num_to_fetch,
                "min_price": getattr(_config, "SHOPPING_MIN_PRICE"),
                "max_price": getattr(_config, "SHOPPING_MAX_PRICE"),
                "json_restrictor": "shopping_results[].{title, product_link, price, source, thumbnail}"
            }

            max_attempts = 3
            base_delay = 0.5

            for attempt in range(1, max_attempts + 1):
                try:
                    start_time = time.time()
                    resp = await self._client.get(self.base_url, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                    # Track search cost
                    _config.cost_logger.track_search(thread_id=thread_id, provider="serpapi")
                    
                    # Write full response to JSON file (overwrites each time)
                    project_root = Path(__file__).parent.parent  # Go up from shopping/ to project root
                    output_dir = project_root / "testing" / "output"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    debug_file = output_dir / "serpapi_response_debug.json"
                    try:
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                    except Exception as write_err:
                        logger.warning("Failed to write SerpApi debug file: %s", write_err)
                    
                    items = data.get("shopping_results", []) or data.get("inline_shopping_results", [])

                    # Normalize ALL results first
                    normalized = normalize_serpapi_results(items)
                    
                    # Apply source filtering to ALL results
                    normalized_filtered = filter_blocked_sources(normalized, _config.BLOCKED_SOURCES)
                    normalized_filtered = filter_by_gender(normalized_filtered, user_gender)
                    
                    # Then cap to what we intend to rank
                    cap = max(_config.SHOPPING_RESULTS_TO_RANK, 1)
                    normalized_capped = cap_results(normalized_filtered, cap)

                    duration = time.time() - start_time
                    logger.info("%d results | %dms | '%s'", len(items), int(duration * 1000), query)
                    return normalized_capped

                except Exception as e:
                    if attempt < max_attempts:
                        # Exponential backoff with jitter
                        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                        logger.warning("SerpApi attempt %d/%d failed for '%s': %s; retrying in %.2fs", attempt, max_attempts, keywords, str(e), delay)
                        await asyncio.sleep(delay)
                        continue
                    logger.error("❌ SerpApi search failed for '%s' after %d attempts", keywords, max_attempts)
                    raise e 