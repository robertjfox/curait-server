import json
import time
import logging
import re
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable, Awaitable, Union, Tuple

logger = logging.getLogger(__name__)


# Streaming response utilities

# based on the following structure i need another function
# that will extract an entire outfit from the response as soon as its done

# Schema shape:
# {
#   "outfits": [
#     {
#       "name": "outfit name",
#       "description": "outfit description", 
#       "items": [
#         {"type": "shirt", "keywords": "red leather jacket"},
#         {"type": "pants", "keywords": "blue suede shoes"},
#         ...
#       ]
#     },
#     ...
#   ]
# }

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
        
        # If full JSON parsing fails, look for complete outfit objects
        # Simple regex to find complete outfit objects with all required fields
        outfit_pattern = r'\{\s*"name"\s*:\s*"[^"]*"\s*,\s*"description"\s*:\s*"[^"]*"\s*,\s*"items"\s*:\s*\[[^\]]*\]\s*\}'
        
        for match in re.finditer(outfit_pattern, response, re.DOTALL):
            try:
                outfit_obj = json.loads(match.group(0))
                # Validate it has all required fields
                if all(key in outfit_obj for key in ["name", "description", "items"]):
                    outfits.append(outfit_obj)
            except json.JSONDecodeError:
                continue
        
        return outfits
        
    except Exception as e:
        logger.error(f"Error extracting outfits from response: {e}")
        return []

async def process_streaming_outfit_response(  
    stream: AsyncGenerator,
    on_outfits: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    start_time: Optional[float] = None,
    grid_size: Optional[int] = None,
) -> Tuple[Dict[str, Any], Optional[Any]]:
    """Process streaming outfit response and extract keywords early for search.
    Calls on_keyword(keyword) immediately when new keywords are detected.
    Calls on_outfits(outfits) when we have accumulated grid_size complete outfits.
    Returns a tuple of (parsed_json, usage) where usage (if present) is the final
    usage object from the last chunk when stream_options={"include_usage": True}.
    """

    full_content = ""
    processed_outfit_names = set()
    batches_sent = 0

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
                                processed_outfit_names.add(name)
                                elapsed_time = time.time() - start_time if start_time else 0
                                logger.info(f"New outfit: {name} in {elapsed_time:.2f}s")
                        
                        # Send batch when we have enough total outfits and haven't sent this batch yet
                        total_outfits = len(current_outfits)
                        if (on_outfits and grid_size and 
                            total_outfits >= grid_size * (batches_sent + 1)):
                            
                            start_idx = batches_sent * grid_size
                            batch = current_outfits[start_idx:start_idx + grid_size]
                            batches_sent += 1
                            logger.info(f"Sending batch {batches_sent} of {total_outfits} outfits")
                            on_outfits(batch)

            except Exception as chunk_error:
                logger.warning(f"Error processing streaming chunk: {chunk_error}")
                continue
                
    except Exception as stream_error:
        logger.error(f"Error processing streaming response: {stream_error}")
        raise stream_error
    
    return json.loads(full_content)
    


