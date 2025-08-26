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

    bg = {
        "item_context": item_context.get("keywords", "") or {},# e.g., intended_gender, palette, budget_band
        "N": N,
    }

    bg_json = json.dumps(bg, separators=(",", ":"))

    system = (
        f"You are a vision ranking model for a single grid image labeled 0..{N-1}. "
        "Use only visual evidence (and any text visible inside the image). "
        "Rules: rate ALL indices; "
        "- assign 3 to ONE produt that is the BEST FIT for the keywords. "
        "- assign 2 if the product is a Good fit, "
        "- assign 1 if the product is a moderate fit, "
        "- assign 0 if it completely doesn't. "
        "Best fit means the product is best out of the options provided. "
        "Good fit means the product is a match for the keywords. "
        "Moderate fit means the product is a moderate match for the keywords, but there is some room for improvement. "
        "Not a match means the product is not a match for the keywords. "
        "Criteria is GENDER & COLOR and PERCIEVED VISUAL QUALITY."
        "If the product thumbnail just looks BAD or CHEAP, assign 0."
        "Give REASONING for each ranking decision, but dont include it in the final output."
        f"Respond ONLY by calling the function `rank_products` with `ratings` = array of {N} integers in [0,1,2,3]. "
        "If you assign 3 to more than one product, you will be penalized."
        "ONLY USE 3,2,1,0 as RATINGS!!!!!"
    )

    user_text = (
        f"3 is the WINNER. 2 is a Good fit, 1 is a moderate fit, 0 is not a match. "
        "Best fit means the product is best out of the options provided. "
        "Return **only** a call to `rank_products(ratings=[...])` with exactly N integers. "
        "Give REASONING for each ranking decision, but dont include it in the final output."
        "Background:" + bg_json
    )

    logger.info(f"User text: {item_context}")

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
