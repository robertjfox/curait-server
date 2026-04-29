import asyncio
from typing import Any, Dict, List, Optional, TypeVar
import httpx
import re
import _config

import logging

logger = logging.getLogger(__name__)


T = TypeVar("T")



def build_query(keywords: Optional[str]) -> str:
    """Sanitize and build a consistent query prefix to bias toward higher quality items."""
    sanitized_keywords = (keywords or "").replace(",", " ").strip()
    sanitized_keywords = re.sub(r"\bcolor\s*:\s*", "", sanitized_keywords, flags=re.IGNORECASE)
    sanitized_keywords = re.sub(r"\bwomens\b", "women", sanitized_keywords, flags=re.IGNORECASE)
    sanitized_keywords = re.sub(r"\bmens\b", "men", sanitized_keywords, flags=re.IGNORECASE)
    sanitized_keywords = re.sub(r"\s+", " ", sanitized_keywords).strip()
    return sanitized_keywords


def cap_results(results: Optional[List[T]], cap: int) -> List[T]:
    """Cap list length safely."""
    if not results:
        return []
    try:
        n = max(1, int(cap))
    except Exception:
        n = 1
    return results[:n]


def create_async_httpx_client(timeout_seconds: float = 15.0) -> httpx.AsyncClient:
    """Create a tuned AsyncClient for external search services."""
    return httpx.AsyncClient(
        http2=False,
        timeout=httpx.Timeout(
            timeout_seconds,
            connect=min(3.0, timeout_seconds),
            read=timeout_seconds,
            write=min(5.0, timeout_seconds),
            pool=min(3.0, timeout_seconds),
        ),
        limits=httpx.Limits(
            max_connections=_config.SEARCH_HTTP_MAX_CONNECTIONS,
            max_keepalive_connections=_config.SEARCH_HTTP_MAX_KEEPALIVE_CONNECTIONS,
        ),
    )


def create_semaphore(max_concurrency: int) -> asyncio.Semaphore:
    return asyncio.Semaphore(max_concurrency)


def filter_blocked_sources(results: List[Dict[str, Any]], blocked_sources: List[str]) -> List[Dict[str, Any]]:
    if not blocked_sources or not results:
        return results
    
    # Normalize blocked sources for matching
    normalized_blocked = []
    for source in blocked_sources:
        if source and isinstance(source, str):
            # Convert to lowercase, remove extra spaces, normalize separators
            normalized = re.sub(r'[^\w\s]', ' ', source.lower().strip())
            normalized = re.sub(r'\s+', ' ', normalized)
            normalized_blocked.append(normalized)
    
    if not normalized_blocked:
        return results
    
    filtered_results = []
    
    for result in results:
        if not isinstance(result, dict):
            continue
            
        title = result.get("title", "") or ""
        source = result.get("source", "") or ""
        
        # Normalize title and source for comparison
        normalized_title = re.sub(r'[^\w\s]', ' ', title.lower().strip())
        normalized_title = re.sub(r'\s+', ' ', normalized_title)
        
        normalized_source = re.sub(r'[^\w\s]', ' ', source.lower().strip())
        normalized_source = re.sub(r'\s+', ' ', normalized_source)
        
        # Check if any blocked source matches
        is_blocked = False
        for blocked in normalized_blocked:
            # For longer blocked terms (4+ chars), use exact substring matching
            if len(blocked) >= 4:
                if (blocked in normalized_source or 
                    blocked in normalized_title):
                    is_blocked = True
                    break
            # For shorter terms, use word boundary matching to avoid false positives
            else:
                # Check if blocked source appears as a complete word or at word boundaries
                pattern = r'\b' + re.escape(blocked) + r'\b'
                if (re.search(pattern, normalized_source) or
                    re.search(pattern, normalized_title)):
                    is_blocked = True
                    break
                
                # Also check if the entire source starts with the blocked term
                if (normalized_source.startswith(blocked + ' ') or
                    normalized_source == blocked):
                    is_blocked = True
                    break
        
        if not is_blocked:
            filtered_results.append(result)
    
    return filtered_results


def filter_by_gender(results: List[Dict[str, Any]], user_gender: Optional[str]) -> List[Dict[str, Any]]:
    if not results or not user_gender:
        return results
    
    gender = user_gender.upper().strip()
    if gender not in ["MALE", "FEMALE"]:
        return results
    
    male_keywords = ["men", "mens", "men's", "man", "male", "masculine", "boys", "boy's"]
    female_keywords = ["women", "womens", "women's", "woman", "female", "feminine", "girls", "girl's", "ladies", "lady's"]
    
    if gender == "MALE":
        exclude_keywords = female_keywords
    else:
        exclude_keywords = male_keywords
    
    filtered_results = []
    
    for result in results:
        if not isinstance(result, dict):
            continue
            
        title = result.get("title", "") or ""
        normalized_title = title.lower().strip()
        
        has_exclude_keywords = any(
            re.search(r'\b' + re.escape(keyword) + r'\b', normalized_title) 
            for keyword in exclude_keywords
        )
        
        if not has_exclude_keywords:
            filtered_results.append(result)
    
    return filtered_results


# needs "reviews" > 9 && "rating" > 4
def filter_by_rating(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered_results = []
    for result in results:
        reviews = result.get("reviews")
        rating = result.get("rating")

        if not reviews or not rating:
            continue

        if reviews > 9 and rating > 4:
            filtered_results.append(result)

    return filtered_results

# Normalization helpers for different providers

def normalize_serpapi_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def normalize_serpapi_item(item: Dict[str, Any]) -> Dict[str, Any]:
        # Ensure price is always a string, provide fallback for None values
        price = item.get("price")
        if price is None:
            price = "Price not available"
        elif not isinstance(price, str):
            price = str(price)
        
        return {
            "title": item.get("title"),
            "price": price,
            # SerpApi uses 'product_link' not 'link'
            "link": item.get("product_link") or item.get("link"),
            # Prefer thumbnail over serpapi_thumbnail, fallback to None
            "imageUrl": item.get("thumbnail") or item.get("serpapi_thumbnail"),
            "source": item.get("source"),
            "rating": item.get("rating"),
            "reviews": item.get("reviews"),
        }

    return [normalize_serpapi_item(it) for it in items or []]