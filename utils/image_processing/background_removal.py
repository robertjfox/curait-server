import hashlib
import httpx
from rembg import remove
from clients.supabase_client import get_supabase_client
import _config
import asyncio
from concurrent.futures import ProcessPoolExecutor
from typing import Optional
import logging
from PIL import Image
from io import BytesIO
import weakref
import atexit

logger = logging.getLogger(__name__)

# Global registry to track active processors for cleanup
_active_processors = weakref.WeakSet()

def _cleanup_all_processors():
    """Cleanup function to ensure all processors are properly closed at exit"""
    for processor in list(_active_processors):
        try:
            if hasattr(processor, '_proc_pool') and processor._proc_pool and not processor._closed:
                processor._proc_pool.shutdown(wait=True)
                logger.debug("Force shutdown ProcessPoolExecutor at exit")
        except Exception as e:
            logger.warning(f"Error during exit cleanup: {e}")

# Register cleanup function
atexit.register(_cleanup_all_processors)

class SupabaseBackgroundProcessor:
    def __init__(self, max_concurrency: int = None, process_workers: Optional[int] = None):
        self._closed = False
        self._proc_pool = None
        self._client = None
        self._active_tasks = set()
        
        try:
            self.supabase = get_supabase_client()
            self.bucket = "processed-bg-removal-imgs"
            max_conc = max_concurrency or _config.BACKGROUND_REMOVAL_MAX_CONCURRENCY
            self.semaphore = asyncio.Semaphore(max_conc)
            self._proc_pool = ProcessPoolExecutor(max_workers=(process_workers if process_workers is not None else _config.BACKGROUND_REMOVAL_PROCESS_WORKERS))
            self._client = httpx.AsyncClient(http2=True, timeout=httpx.Timeout(30.0))
            
            # Register this processor for cleanup
            _active_processors.add(self)
            
        except Exception:
            # If initialization fails, ensure cleanup of any partially created resources
            self._closed = True
            if self._proc_pool:
                self._proc_pool.shutdown(wait=False)
            if self._client:
                # Can't await in __init__, so just close synchronously 
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._client.aclose())
                    else:
                        loop.run_until_complete(self._client.aclose())
                except:
                    pass
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __del__(self):
        """Ensure ProcessPoolExecutor is shutdown when object is garbage collected"""
        if hasattr(self, '_proc_pool') and self._proc_pool and not self._closed:
            try:
                self._proc_pool.shutdown(wait=False)
                logger.debug("ProcessPoolExecutor shutdown in destructor")
            except Exception:
                pass

    @staticmethod
    def _resize_image_bytes(image_bytes: bytes, max_dim: int) -> bytes:
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                img = img.convert('RGBA')
                w, h = img.size
                scale = min(1.0, max_dim / max(w, h))
                if scale < 1.0:
                    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                    img = img.resize(new_size, Image.LANCZOS)
                out = BytesIO()
                img.save(out, format='PNG')
                return out.getvalue()
        except Exception:
            return image_bytes

    async def _exists_public(self, filename: str) -> Optional[str]:
        try:
            url = self.supabase.storage.from_(self.bucket).get_public_url(filename)
            resp = await self._client.head(url, follow_redirects=True)
            if resp.status_code == 200:
                return url
        except Exception:
            return None
        return None

    async def process_image(self, image_url: str, max_retries: int = 2) -> str:
        if self._closed:
            logger.warning("Background processor is closed, returning original URL")
            return image_url
            
        async with self.semaphore:
            short = image_url[:80]
            for attempt in range(max_retries + 1):
                try:
                    filename = f"{hashlib.md5(image_url.encode()).hexdigest()}.png"

                    existing_url = await self._exists_public(filename)
                    if existing_url:
                        return existing_url

                    resp = await self._client.get(image_url)
                    resp.raise_for_status()
                    input_bytes = resp.content

                    if _config.BACKGROUND_REMOVAL_MAX_DIM:
                        loop = asyncio.get_running_loop()
                        # Add timeout to prevent hanging executor tasks
                        resized_bytes = await asyncio.wait_for(
                            loop.run_in_executor(
                                None, self._resize_image_bytes, input_bytes, _config.BACKGROUND_REMOVAL_MAX_DIM
                            ),
                            timeout=30.0
                        )
                        if resized_bytes:
                            input_bytes = resized_bytes

                    loop = asyncio.get_running_loop()
                    # Add timeout to prevent hanging background removal tasks
                    processed_bytes = await asyncio.wait_for(
                        loop.run_in_executor(self._proc_pool, remove, input_bytes),
                        timeout=60.0
                    )

                    def _upload():
                        return self.supabase.storage.from_(self.bucket).upload(
                            filename,
                            processed_bytes,
                            file_options={"content-type": "image/png"}
                        )
                    await asyncio.wait_for(
                        loop.run_in_executor(None, _upload),
                        timeout=30.0
                    )

                    def _public_url():
                        return self.supabase.storage.from_(self.bucket).get_public_url(filename)
                    public_url = await asyncio.wait_for(
                        loop.run_in_executor(None, _public_url),
                        timeout=10.0
                    )
                    return public_url

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout processing image {short}... on attempt {attempt + 1}")
                    if attempt == max_retries:
                        return image_url
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"Error processing image {short}... on attempt {attempt + 1}: {e}")
                    if attempt == max_retries:
                        return image_url
                    await asyncio.sleep(1)
        return image_url

    async def close(self):
        """Close the background processor and clean up resources"""
        if self._closed:
            return
            
        logger.debug("Closing SupabaseBackgroundProcessor...")
        self._closed = True
        
        # Cancel any active tasks
        if self._active_tasks:
            for task in list(self._active_tasks):
                if not task.done():
                    task.cancel()
            
            # Wait for cancelled tasks to complete with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._active_tasks, return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for active tasks to complete")
        
        if self._client:
            try:
                await self._client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")
        
        if self._proc_pool:
            try:
                # Properly shutdown the process pool and wait for workers to complete
                # This prevents semaphore leakage by ensuring all processes finish cleanly
                loop = asyncio.get_running_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._proc_pool.shutdown, True),
                    timeout=10.0
                )
                logger.debug("ProcessPoolExecutor shutdown completed")
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for ProcessPoolExecutor shutdown, forcing shutdown")
                try:
                    self._proc_pool.shutdown(wait=False)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Error shutting down ProcessPoolExecutor: {e}")
                # Force shutdown if graceful shutdown fails
                try:
                    self._proc_pool.shutdown(wait=False)
                except Exception:
                    pass 