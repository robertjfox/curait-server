import os
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple

from clients.shopping.serper_client import SerperShoppingClient
from clients.shopping.serpapi_client import SerpApiShoppingClient
import _config as config

logger = logging.getLogger(__name__)


class ShoppingService:
	"""Shopping facade that picks Serper/SerpApi based on SEARCH_PROVIDER env.

	A single instance is shared across the whole process via
	:func:`get_shopping_service` so we hold exactly one outbound httpx
	client (and one Serper concurrency semaphore) for the lifetime of the
	server. Previously ``OutfitGenerationService`` was constructed three
	times at import (in routers/threads.py, routers/outfits.py, and
	thread_service.py), each creating its own httpx client which never got
	closed. That stacked file descriptors and TCP connections every time
	the server hot-reloaded.
	"""

	def __init__(self):
		self._provider = os.getenv("SEARCH_PROVIDER", "serper").lower().strip()
		self._client = None

		if self._provider == "serpapi":
			try:
				self._client = SerpApiShoppingClient()
			except ImportError:
				logger.warning("SerpApi client not available, falling back to Serper")
				self._provider = "serper"

		if self._provider == "serper" or self._client is None:
			self._client = SerperShoppingClient()

	async def search_for_keywords(
		self,
		keywords: str,
		user_data: Dict[str, Any],
	) -> Tuple[List[Dict[str, Any]], int, int]:
		"""Search for products using the configured provider."""
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
		if self._client:
			await self._client.aclose()
			self._client = None


_service: Optional[ShoppingService] = None


def get_shopping_service() -> ShoppingService:
	global _service
	if _service is None:
		_service = ShoppingService()
	return _service


async def close_shopping_service() -> None:
	global _service
	if _service is None:
		return
	service = _service
	_service = None
	await service.aclose()
