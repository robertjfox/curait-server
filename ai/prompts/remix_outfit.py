import json
from typing import Any, Dict, List


def build_remix_outfit_messages(
    *,
    user_data: Dict[str, Any],
    existing_outfit: Dict[str, Any],
    existing_items: List[Dict[str, Any]],
    feedback: str,
) -> List[Dict[str, Any]]:
    item_context = []
    for item in existing_items:
        products = item.get("search_results") or []
        item_context.append(
            {
                "id": item.get("id") or "",
                "type": item.get("type") or "",
                "keywords": item.get("keywords") or "",
                "product_count": len(products),
                "sample_products": [
                    {
                        "title": product.get("title") or "",
                        "source": product.get("source") or "",
                        "price": product.get("price") or "",
                    }
                    for product in products[:3]
                ],
            }
        )

    context = {
        "user": user_data,
        "outfit": {
            "id": existing_outfit.get("id"),
            "name": existing_outfit.get("name"),
        },
        "items": item_context,
        "feedback": feedback,
    }

    system = (
        "You are a fashion remix planner. Revise one existing outfit based on user feedback.\n"
        "Keep any item that the feedback does not need to change. Mark those items action='keep' and preserve their source_item_id.\n"
        "Only mark action='change' for items that must be researched again or materially changed.\n"
        "If the user asks to change pants to light jeans, keep the shirt/jacket/shoes unless they conflict.\n"
        "Return one complete outfit with 3-5 main clothing/shoe items. No hats, bags, jewelry, glasses, belts, or accessories.\n"
        "Keywords must be concise shopping search phrases, space-delimited, no commas."
    )

    user = (
        "Create the remixed outfit. Keep product reuse high when possible.\n"
        "Context JSON:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
