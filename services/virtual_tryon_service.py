import httpx
from io import BytesIO
from typing import List, Dict, Any, Optional
import _config
import base64
import uuid
from supabase import create_client, Client
import logging

from clients.openai_client import get_openai_client
import time
from utils.logging.terminal_links import hyperlink
from utils.image_processing.thumbnail_compressor import compress_thumbnails_to_grid
from utils.image_processing.user_selfie_handler import get_user_selfie_url
import asyncio

logger = logging.getLogger(__name__)

class VirtualTryOnService:
    
    _logged_prompt_once: bool = False

    def __init__(self):
        self.openai_client = get_openai_client()
        self.supabase: Client = create_client(_config.SUPABASE_URL, _config.SUPABASE_KEY)
    
    async def generate_virtual_tryon(
        self, 
        item_products: List[Dict[str, Any]],
        gender: Optional[str] = None,
        user_data: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:

        start_time = time.time()
        
        images, grid_url = await self._prepare_inputs_and_log(
            item_products, gender, user_data
        )

        response = await asyncio.wait_for(
            self.openai_client.virtual_tryon_flow(
                image=images[0] if len(images) == 1 else images,
                gender=gender,
                user_data=user_data,
                thread_id=thread_id,
            ),
            timeout=_config.VIRTUAL_TRYON_TIMEOUT,
        )

        image_url = await self._process_response(response, start_time, grid_url, user_id)
        return {"image_url": image_url}
            

    async def _prepare_inputs_and_log(self, item_products: List[Dict], gender: Optional[str], 
                            user_data: Optional[Dict]):
        """Create grid, log products, and prepare prompt - all in one step"""
        gender_text = f" ({gender})" if gender else ""
        
        # Create grid (single source of truth)
        result = await compress_thumbnails_to_grid(item_products, [], user_data=user_data)
        
        grid_bytes, grid_url = result
        grid_image = BytesIO(grid_bytes)
        grid_image.name = "product_grid.jpg"
        
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
        
        logger.info(f"STARTING GENERATE VTON | {gender_text}{pairs_text}")
        
        # Generate prompt (for logging only)
        from ai.prompts.virtual_tryon import generate_virtual_tryon_prompt
        prompt = generate_virtual_tryon_prompt(
            gender=gender or "female",
            user_data=user_data,        
        )

        return [grid_image], prompt, grid_url

    async def _process_response(self, response, start_time: float, grid_url: Optional[str] = None, user_id: Optional[str] = None) -> str:
        item = response.data[0]
        
        if hasattr(item, 'b64_json') and item.b64_json:
            image_bytes = base64.b64decode(item.b64_json)
        elif hasattr(item, 'url') and item.url:
            async with httpx.AsyncClient() as client:
                resp = await client.get(item.url)
                resp.raise_for_status()
                image_bytes = resp.content
        
        user_face_url = None
        source_key = "user_default"
        
        # Try to get user-specific selfie using user_id
        if user_id:
            filename = f"user_face_{user_id}.png"
            source_key = f"user_{user_id}"
            try:
                user_face_url = get_user_selfie_url(filename)
            except Exception:
                user_face_url = None
        
        if _config.FACE_SWAP_ENABLED and user_face_url:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(user_face_url)
                    resp.raise_for_status()
                    user_face_bytes = resp.content
                
                from utils.image_processing.face_injector import FaceInjector, restore_faces_bytes
                face_injector = FaceInjector.instance()
                loop = asyncio.get_running_loop()
                
                image_bytes = await loop.run_in_executor(None, lambda: face_injector.swap_to_bytes(
                    source_key=source_key, source_bytes=user_face_bytes, target_bytes=image_bytes
                ))
                
                try:
                    image_bytes = await loop.run_in_executor(None, lambda: restore_faces_bytes(image_bytes))
                except Exception as restore_error:
                    logger.warning(f"Face restoration failed: {restore_error}")
                    
            except Exception as e:
                logger.warning(f"Face swap failed: {e}")
        elif not _config.FACE_SWAP_ENABLED:
            logger.info("FACE_SWAP_ENABLED is false; skipping face swapping step")
        
        filename = f"virtual_tryon_{uuid.uuid4()}.png"

        self.supabase.storage.from_("virtual-tryon-images").upload(
            path=filename, file=image_bytes, file_options={"content-type": "image/png"}
        )
        url = self.supabase.storage.from_("virtual-tryon-images").get_public_url(filename)
        
        duration = time.time() - start_time
        grid_link = f" | {hyperlink(grid_url, 'View Input Grid')}" if grid_url else ""
        logger.info(f"COMPLETE | {duration:.2f}s | {hyperlink(url, 'View Result')}{grid_link}")
        
        return url



    
 