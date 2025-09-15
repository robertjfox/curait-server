import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

def build_product_ranking_prompt(
    user_data: Dict[str, Any],
    item_context: Dict[str, Any],
    num_results: int,
    *,
    grid_image_data_uri: str,
) -> List[Dict[str, Any]]:
    N = num_results

    # Compact background for fewer tokens
    bg = {
        "k": item_context.get("keywords") or "",
        "g": (user_data.get("gender") or "unspecified").lower(),
        "n": N,
    }
    bg_json = json.dumps(bg, separators=(",", ":"))

    system = (
        f"You rank products in one grid labeled 0..{N-1}.\n"
        "Use only visual cues (and any text shown inside the image).\n"
        "Score EVERY index with integers in [0,1,2,3]: "
        "3=single best overall match, 2=good match, 1=partial, 0=not a match/looks cheap/wrong gender or color.\n"
        "Criteria: gender, color, visual quality. Pick the best match and the coolest product.\n"
        "Exactly one 3 (pick the closest if none are perfect).\n"
        f"Reply ONLY with rank_products(ratings=[{N} ints]). No prose."
    )

    user_text = (
        "Return only rank_products(ratings=[...]) with exactly N integers.\n"
        "Background:" + bg_json
    )

    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": grid_image_data_uri, "detail": "low"}},
            ],
        },
    ]
