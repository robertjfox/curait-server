import json
import time
import logging
import re
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable, Awaitable, Union, Tuple

logger = logging.getLogger(__name__)

def extract_outfits_from_response(response: str) -> List[Dict[str, Any]]:
    """Extract all complete outfits from the response.
    
    Returns a list of outfit objects that are complete and valid.
    """
    outfits = []
    
    try:
        # First, try to parse the entire response as complete JSON
        try:
            parsed = json.loads(response)
            if isinstance(parsed, dict) and "outfits" in parsed and parsed["outfits"]:
                return parsed["outfits"]
        except json.JSONDecodeError:
            pass
        
        # Match minimal outfit objects with name and items (no description required)
        outfit_pattern = r'\{\s*"name"\s*:\s*"[^"]*"\s*,\s*"items"\s*:\s*\[[^\]]*\]\s*\}'
        
        for match in re.finditer(outfit_pattern, response, re.DOTALL):
            try:
                outfit_obj = json.loads(match.group(0))
                # Validate it has required fields
                if all(key in outfit_obj for key in ["name", "items"]):
                    outfits.append(outfit_obj)
            except json.JSONDecodeError:
                continue
        
        return outfits
        
    except Exception as e:
        logger.error(f"Error extracting outfits from response: {e}")
        return []

async def process_streaming_outfit_response(  
    stream: AsyncGenerator,
    on_single_outfit: Optional[Callable[[Dict[str, Any]], Callable[[str], None]]] = None,
    on_outfit_batch: Optional[Callable[[List[Dict[str, Any]], List[str]], None]] = None,
    start_time: Optional[float] = None,
    grid_size: Optional[int] = None,
) -> Tuple[Dict[str, Any], Optional[Any]]:
    """Process streaming outfit response and extract keywords early for search.
    Calls on_keyword(keyword) immediately when new keywords are detected.
    Calls on_outfit_batch(outfits) when we have accumulated grid_size complete outfits.
    Returns a tuple of (parsed_json, usage) where usage (if present) is the final
    usage object from the last chunk when stream_options={"include_usage": True}.
    """

    full_content = ""
    processed_outfit_names = set()
    
    # Shared array to collect outfits and their IDs
    outfit_batch_queue = []  # List of {"outfit": outfit_dict, "outfit_id": str}
    outfit_count = 0
    
    def register_completed_outfit(outfit: Dict[str, Any], outfit_id: str) -> None:
        """Called by on_single_outfit when an outfit is fully processed."""
        outfit_batch_queue.append({"outfit": outfit, "outfit_id": outfit_id})
        # Check if we have enough for a batch
        if grid_size and len(outfit_batch_queue) >= grid_size:
            # Extract outfits and IDs for batching
            batch_outfits = [item["outfit"] for item in outfit_batch_queue[:grid_size]]
            batch_outfit_ids = [item["outfit_id"] for item in outfit_batch_queue[:grid_size]]
            
            # Remove processed items from queue
            outfit_batch_queue[:grid_size] = []
            
            if on_outfit_batch:
                on_outfit_batch(batch_outfits, batch_outfit_ids)

    try:
        async for chunk in stream:
            try:
                # Capture usage if provided on the last chunk
                if getattr(chunk, "usage", None) is not None:
                    final_usage = chunk.usage
                
                # Some stream events may not include choices (e.g., usage-only events)
                choices = getattr(chunk, "choices", None)
                if not choices or len(choices) == 0:
                    continue

                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None)

                if content:
                    full_content += content

                    if len(full_content) > 50:
                        # Check for new outfits
                        current_outfits = extract_outfits_from_response(full_content)
                        
                        # Find and log truly new outfits
                        for outfit in current_outfits:
                            name = outfit.get("name")
                            if name and name not in processed_outfit_names:
                                outfit_count += 1
                                processed_outfit_names.add(name)
                                elapsed_time = time.time() - start_time if start_time else 0
                                logger.info(f"New outfit: {name} in {elapsed_time:.2f}s")
                                if on_single_outfit:
                                    # Pass the outfit and the register callback
                                    on_single_outfit(outfit, register_completed_outfit, outfit_count)

            except Exception as chunk_error:
                logger.warning(f"Error processing streaming chunk: {chunk_error}")
                continue
                
    except Exception as stream_error:
        logger.error(f"Error processing streaming response: {stream_error}")
        raise stream_error
    
    return json.loads(full_content)
    


