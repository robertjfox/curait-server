import json
import logging
import re
import asyncio
from typing import Dict, Any, List, Optional, AsyncGenerator

log = logging.getLogger(__name__)


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


async def process_streaming_outfit_response(
    stream: AsyncGenerator,
    num_outfits: int,
    num_items: int,
    early_search_callback: Optional[callable] = None
) -> str:
    """Process streaming outfit response and extract keywords early for search."""
    full_content = ""
    processed_keywords = set()  # Track which keywords we've already processed
    
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            content_chunk = chunk.choices[0].delta.content
            full_content += content_chunk
            
            # Continuously extract new keywords as content grows
            if len(full_content) > 100 and early_search_callback:  # Lower threshold
                keywords = extract_keywords_from_partial_json(full_content)
                if keywords:
                    # Only process new keywords we haven't seen before
                    new_keywords = [kw for kw in keywords if kw not in processed_keywords]
                    if new_keywords:
                        processed_keywords.update(new_keywords)
                        asyncio.create_task(early_search_callback(new_keywords))
    
    return full_content


def parse_final_outfit_json(content: str) -> Dict[str, Any]:
    """Parse final outfit JSON with fallback handling."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON if model included extra text
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            raise ValueError("Failed to parse outfit generation response as JSON") 