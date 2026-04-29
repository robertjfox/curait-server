import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

def build_product_ranking_prompt(
    *,
    user_data: Dict[str, Any],
    item_context: Dict[str, Any],
    products: List[Dict[str, Any]],
    num_results: int,
    grid_image_data_uri: str,
    outfit_row: Dict[str, Any],
) -> List[Dict[str, Any]]:
    N = num_results
    # Compact background for fewer tokens
    bg = {
        "keywords": item_context.get("keywords") or "",
        "gender": (user_data.get("gender") or "unspecified").lower(),
        "num_results": N,
        "outfit_name": outfit_row.get("name") or "",
    }
    product_meta = [
        {
            "index": i,
            "title": str(product.get("title") or "")[:180],
            "source": str(product.get("source") or "")[:60],
            "price": str(product.get("price") or "")[:40],
        }
        for i, product in enumerate(products[:N])
    ]
    
    bg_json = json.dumps(bg, separators=(",", ":"))
    product_json = json.dumps(product_meta, separators=(",", ":"))

    system = (
        f"You rank shopping products in one grid labeled 0..{N-1}.\n"
        "Use the product image, the product title metadata, and the ranking goal.\n"
        "Score EVERY index with an integer from 0 to 3:\n"
        "3 = strong match for item type, color/material, and outfit intent.\n"
        "2 = acceptable match; close enough to show the user.\n"
        "1 = weak match, but still plausibly useful.\n"
        "0 = clearly wrong product type or unusable result.\n"
        "Do not collapse to all zeros unless every item is truly the wrong category. "
        "When the search query already contains the intended color/type, assume most reasonable results are at least 1.\n"
        f"Reply ONLY with JSON matching the schema: ratings is an array of exactly {N} integers."
    )

    user_text = (
        "Return only JSON with exactly N integer ratings.\n"
        "Background:" + bg_json + "\n"
        "Products:" + product_json
    )

    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": grid_image_data_uri, "detail": "auto"}},
            ],
        },
    ]
