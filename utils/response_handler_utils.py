import json
import logging
import re
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator

logger = logging.getLogger(__name__)


# Streaming response utilities
def extract_keywords_from_partial_json(partial_content: str) -> Optional[List[str]]:
    """Extract ALL keywords found from partial streaming JSON content across all outfits."""
    try:
        import _config
        num_outfits = getattr(_config, "NUM_OUTFITS_TO_GENERATE", 1)
        num_items = getattr(_config, "NUM_ITEMS_PER_OUTFIT", 1)
        
        keywords = []
        
        # Look for all outfit sections
        for outfit_num in range(1, num_outfits + 1):
            outfit_key = f'"outfit_{outfit_num}"'
            outfit_start = partial_content.find(outfit_key)
            
            if outfit_start != -1:
                # Find the opening brace for this outfit
                brace_start = partial_content.find('{', outfit_start)
                if brace_start != -1:
                    # Find the end of this outfit section (next outfit or end)
                    next_outfit_key = f'"outfit_{outfit_num + 1}"' if outfit_num < num_outfits else '"metadata"'
                    next_outfit_start = partial_content.find(next_outfit_key, brace_start)
                    
                    # Extract from this outfit section
                    outfit_section = partial_content[brace_start:next_outfit_start] if next_outfit_start != -1 else partial_content[brace_start:]
                    
                    # Look for all item keywords in this outfit
                    for item_num in range(1, num_items + 1):
                        # Match pattern: "item_X": "keyword string"
                        item_pattern = f'"item_{item_num}":\\s*"([^"]*)"'
                        match = re.search(item_pattern, outfit_section)
                        if match:
                            keyword = match.group(1).strip()
                            if keyword:  # Only add non-empty keywords
                                keywords.append(keyword)
        
        # Return any keywords found, don't wait for a threshold
        return keywords if keywords else None
        
    except Exception as e:
        logger.error(f"Error extracting keywords from partial JSON: {e}")
        return None

def extract_metadata_from_json(content: str) -> Optional[Dict[str, Any]]:
    """Extract metadata from JSON content as simply as possible."""
    try:
        data = json.loads(content)
        return data.get("metadata") if isinstance(data, dict) else None
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON content")
        return None


async def process_streaming_outfit_response(
    stream: AsyncGenerator,
    item_db_ids: List[str],
    _process_single_item_cb: Optional[callable] = None
) -> Dict[str, Any]:
    """Process streaming outfit response and extract keywords early for search."""
    full_content = ""
    processed_keywords = set()

    remaining_item_ids = item_db_ids.copy()

    try:
        async for chunk in stream:
            try:
                if chunk.choices[0].delta.content:
                    content_chunk = chunk.choices[0].delta.content
                    full_content += content_chunk

                    # Continuously extract new keywords as content grows
                    if len(full_content) > 100:  # Lower threshold
                        keywords = extract_keywords_from_partial_json(full_content)
                        if keywords:
                            # Only process new keywords we haven't seen before
                            new_keywords = [kw for kw in keywords if kw not in processed_keywords]

                            for new_keyword in new_keywords:
                                processed_keywords.add(new_keyword)
                                if remaining_item_ids:
                                    next_item_id = remaining_item_ids.pop(0)
                                    asyncio.create_task(_process_single_item_cb(new_keyword, next_item_id))
                                else:
                                    logger.warning(f"No more item IDs available for keyword: {new_keyword}")
            except Exception as chunk_error:
                logger.warning(f"Error processing streaming chunk: {chunk_error}")
                # Continue processing other chunks
                continue
                
    except Exception as stream_error:
        logger.error(f"Error processing streaming response: {stream_error}")
        # If we have partial content, try to extract metadata from it
        if full_content:
            logger.info("Attempting to extract metadata from partial content")
        else:
            logger.error("No content received before stream error")
            raise stream_error
    
    # return the metadata section of the full content as a dict
    return extract_metadata_from_json(full_content)
    


