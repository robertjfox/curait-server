import json
from typing import Any, Dict, List

def build_product_ranking_prompt(
    user_data: Dict[str, Any],
    item_context: Dict[str, Any],
    num_results: int,
    *,
    grid_image_data_uri: str,
) -> List[Dict[str, Any]]:
    N = num_results
    profile = {k: v for k, v in (user_data or {}).items() if k != "context"}
    bg = {
        "user_profile": profile,           # keep lean; or {}
        "item_context": item_context or {},# e.g., intended_gender, palette, budget_band
        "N": N,
    }
    bg_json = json.dumps(bg, separators=(",", ":"))

    system = (
        f"You are a vision ranking model for a single grid image labeled 0..{N-1}. "
        "Use only visual evidence (and any text visible inside the image). "
        "Rules: rate ALL indices; gender mismatch→1; missing signals=neutral; 0-based indexing. "
        "Weights: Color=35 Vibe=50 Brand=15"
        "Try to capture the overall vibe of the user based on their profile info."
        f"Respond ONLY by calling the function `rank_products` with `ratings` = array of {N} integers in [1,10]. "
        "Do NOT output text or JSON in assistant content."
    )

    user_text = (
        f"Rate all {N} products (0..{N-1}) in the grid. Ties allowed. "
        "If unreadable/blocked → conservative (≤4). "
        "Return **only** a call to `rank_products(ratings=[...])` with exactly N integers. "
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
