from typing import List, Dict, Any, Optional
import uuid
import logging
import time
import asyncio

from clients.gemini_client import get_gemini_client
from clients.supabase_client import get_supabase_client
from utils.logging.terminal_links import hyperlink
from utils.image_processing.thumbnail_compressor import compress_thumbnails_to_grid

logger = logging.getLogger(__name__)


class VirtualTryOnService:

	def __init__(self):
		self.gemini_client = get_gemini_client()
		self.supabase = get_supabase_client()

	async def generate_virtual_tryon(
		self,
		item_products: List[Dict[str, Any]],
		user_id: str,
	) -> Dict[str, Any]:
		start_time = time.time()

		grid_bytes, grid_url = await self._prepare_grid_and_log(item_products)

		# Gemini call is sync; run in a worker thread.
		image_bytes = await asyncio.to_thread(
			self.gemini_client.generate_virtual_tryon,
			grid_bytes=grid_bytes,
			user_id=user_id,
		)

		image_url = await self._upload_and_log(image_bytes, start_time, grid_url)
		return {"image_url": image_url}

	async def _prepare_grid_and_log(self, item_products: List[Dict]):
		"""Create grid and log products."""
		result = await compress_thumbnails_to_grid(item_products)
		grid_bytes, grid_url = result

		product_links = []
		for product in item_products:
			title = product.get("title", "Unknown Item")
			url = product.get("imageUrl", "")
			if url:
				product_links.append(f"  • {hyperlink(url, title)}")
			else:
				product_links.append(f"  • {title}")

		pairs_text = "\n" + "\n".join(product_links)
		if grid_url:
			pairs_text += f"\n  • Grid: {hyperlink(grid_url, 'View 2x2 grid')}"

		logger.info(f"STARTING GENERATE VTON |{pairs_text}")

		return grid_bytes, grid_url

	async def _upload_and_log(
		self,
		image_bytes: bytes,
		start_time: float,
		grid_url: Optional[str] = None,
	) -> str:
		filename = f"virtual_tryon_{uuid.uuid4()}.png"

		def _upload() -> str:
			storage = self.supabase.storage.from_("virtual-tryon-images")
			storage.upload(
				path=filename,
				file=image_bytes,
				file_options={"content-type": "image/png"},
			)
			return storage.get_public_url(filename)

		# Supabase storage SDK is sync; run in a worker thread.
		url = await asyncio.to_thread(_upload)

		duration = time.time() - start_time
		grid_link = f" | {hyperlink(grid_url, 'View Input Grid')}" if grid_url else ""
		logger.info(f"COMPLETE | {duration:.2f}s | {hyperlink(url, 'View Result')}{grid_link}")

		return url


_service: Optional[VirtualTryOnService] = None


def get_virtual_tryon_service() -> VirtualTryOnService:
	global _service
	if _service is None:
		_service = VirtualTryOnService()
	return _service
