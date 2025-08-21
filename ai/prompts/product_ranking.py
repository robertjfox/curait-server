from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

def build_product_ranking_prompt(
    user_data: Dict[str, Any],
    item_context: Dict[str, Any],
    num_results: int,
    *,
    grid_image_data_uri: str,
) -> List[Dict[str, Any]]:
    """
    Build messages for re-ranking shopping results using ONLY the visual grid image.
    The model must return JSON matching this schema:
    { "ratings": int[1..10] } where ratings has exactly n integers (1..10), n = number of products.
    """
    
    system = (
        "You are a visual shopping ranking assistant."
        " You will be shown a grid of product images with numbered labels (0, 1, 2, etc.)."
        " Evaluate ALL products based on visual assessment to best match the user context and item requirements."
        " Return JSON only with a single key `ratings`, an array of exactly n integers (1..10)."
        " Rate every product; do not omit any indices."
        " Higher numbers mean better overall match."
        " Return only valid JSON (no code block, no commentary)."
        "\n\nHard constraint: gender must match. If a product is clearly for the other gender (e.g., labeled 'mens' vs 'womens', male vs female),"
        " assign rating = 1 regardless of other factors. Use user/item context for intended gender and the image/title overlays to infer product gender."
        "\n\nWeighting for each rating (target proportions, internal to your reasoning):"
        " color match 35%, vibe/style match 35%, brand/retailer reputation 15%, price fit 15%."
        "\n- Color match: Prefer items whose visible colors align with the item keywords or stated preferences."
        "\n- Vibe/style match: Prefer items whose silhouette, cut, and overall aesthetic match the requested item context (e.g., minimalist, streetwear, workwear)."
        "\n- Brand/retailer reputation: Prefer well-known, reputable brands or retailers."
        "\n- Price fit: Prefer prices that fit the user's budget preference (e.g., price_range: affordable/medium/luxury or numeric budget if provided)."
        "\nIf any signal is missing, treat it as neutral (do not penalize)."
    )

    # Just dump the raw data as JSON for the AI to handle, but segmented
    import json
    
    safe_user: Dict[str, Any] = user_data or {}
    profile: Dict[str, Any] = {k: v for k, v in safe_user.items() if k != "context"}
    ctx: Dict[str, Any] = (safe_user.get("context") or {}) if isinstance(safe_user.get("context"), dict) else {}
    segmented_context: Dict[str, Any] = {
        "body_context": ctx.get("body_context", {}),
        "lifestyle_context": ctx.get("lifestyle_context", {}),
        "style_context": ctx.get("style_context", {}),
    }

    context_data = {
        "user_profile": profile,
        "user_context": segmented_context,
        "item_context": item_context or {},
    }
    
    context_json = json.dumps(context_data, indent=2)

    text_instr = (
        f"Rate the {num_results} products shown in the grid image. Evaluate all items before scoring."
        f" Match the intended gender from context; if a product is for a different gender, set its rating to 1."
        f"\n\nUse these weights in your reasoning: color 35%, vibe 35%, brand 15%, price 15%."
        f"\n\nContext (segmented):\n{context_json}\n\n"
        f"Return JSON ONLY: {{ \"ratings\": [int 1..10] }} with exactly {num_results} integers,"
        f" where ratings[i] is for product i (0-based)."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text_instr},
                {"type": "image_url", "image_url": {"url": grid_image_data_uri}},
            ],
        }
    ]

    return messages 