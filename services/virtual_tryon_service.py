from io import BytesIO
from typing import List, Dict, Any, Optional
import _config
import uuid
from supabase import create_client, Client
import logging

from clients.gemini_client import get_gemini_client
import time
from utils.logging.terminal_links import hyperlink
from utils.image_processing.thumbnail_compressor import compress_thumbnails_to_grid
import asyncio

logger = logging.getLogger(__name__)

class VirtualTryOnService:
    
    def __init__(self):
        self.gemini_client = get_gemini_client()
        self.supabase: Client = create_client(_config.SUPABASE_URL, _config.SUPABASE_KEY)
    
    async def generate_virtual_tryon(self, item_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        start_time = time.time()
        
        grid_bytes, grid_url = await self._prepare_grid_and_log(item_products)

        # Generate with Gemini using just the product grid
        image_bytes = await asyncio.to_thread(
            lambda: self.gemini_client.generate_virtual_tryon(grid_bytes=grid_bytes)
        )

        image_url = await self._upload_and_log(image_bytes, start_time, grid_url)
        return {"image_url": image_url}
            

    async def _prepare_grid_and_log(self, item_products: List[Dict]):
        """Create grid and log products."""
        
        # Create grid without face overlay
        result = await compress_thumbnails_to_grid(item_products)
        grid_bytes, grid_url = result
        
        # Log product information
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

    async def _upload_and_log(self, image_bytes: bytes, start_time: float, grid_url: Optional[str] = None) -> str:
        filename = f"virtual_tryon_{uuid.uuid4()}.png"

        self.supabase.storage.from_("virtual-tryon-images").upload(
            path=filename, file=image_bytes, file_options={"content-type": "image/png"}
        )
        url = self.supabase.storage.from_("virtual-tryon-images").get_public_url(filename)
        
        duration = time.time() - start_time
        grid_link = f" | {hyperlink(grid_url, 'View Input Grid')}" if grid_url else ""
        logger.info(f"COMPLETE | {duration:.2f}s | {hyperlink(url, 'View Result')}{grid_link}")
        
        return url



    
 