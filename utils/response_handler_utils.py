import json
import logging
import re
from typing import Dict, Any, List, Optional, AsyncGenerator, Callable, Awaitable, Union

logger = logging.getLogger(__name__)


# Streaming response utilities

def extract_keywords_from_partial_json(partial_content: str) -> Optional[List[str]]:
    """Extract item-level keywords from partial streaming JSON content.
    New format expects keywords embedded within outfits[*].items[*].keywords.
    """
    try:
        # Best-effort regex to capture values of "keywords": "..."
        # Avoids matching property names by targeting the value after the colon
        matches = re.findall(r'"keywords"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', partial_content)
        keywords = [m.strip() for m in matches if m.strip()]
        return keywords if keywords else None
    except Exception as e:
        logger.warning(f"Error extracting keywords from partial JSON: {e}")
        return None


async def process_streaming_outfit_response(            
    stream: AsyncGenerator,
    on_keyword: Optional[Union[Callable[[str], None], Callable[[str], Awaitable[None]]]] = None,
) -> Dict[str, Any]:
    """Process streaming outfit response and extract keywords early for search.
    Calls on_keyword(keyword) immediately when new keywords are detected.
    """
    full_content = ""
    processed_keywords = set()

    try:
        async for chunk in stream:
            try:
                if chunk.choices[0].delta.content:
                    full_content += chunk.choices[0].delta.content

                    if len(full_content) > 50:
                        keywords = extract_keywords_from_partial_json(full_content)
                        if keywords:
                            new_keywords = [kw for kw in keywords if kw not in processed_keywords]

                            for new_keyword in new_keywords:
                                processed_keywords.add(new_keyword)

                                on_keyword(new_keyword)

            except Exception as chunk_error:
                logger.warning(f"Error processing streaming chunk: {chunk_error}")
                continue
                
    except Exception as stream_error:
        logger.error(f"Error processing streaming response: {stream_error}")
        raise stream_error
    
    return json.loads(full_content)
    


