from typing import List, Dict, Any

import _config as config


def build_explore_ideas_input(*, gender: str, date_iso: str, outfit_items: List[Dict[str, str]], source_img_url: str = None) -> str:
    instructions = (
        "You are a fashion trend analyst tasked with distilling a compelling styling concept from a trend outfit. "
        "Your goal is to identify the underlying TREND that this outfit represents. "
        "DONT be specifc to items, rather the vibe, materials, color palette, etc."
        "No specific colors.  Palettes are OK, but not specific colors."
        "Give a sense of the type of items that might be used, but be somewhat general."

        "\n\nAnalyze the outfit items and extract the core trend concept that connects them. Consider:"
        "\n• What styling philosophy does this combination represent?"
        "\n• What aesthetic movement or trend does it embody?"
        "\n• What occasion, mood, or lifestyle does it suggest?"
        "\n• What makes this combination trend-worthy and influential?"
        "\n\nDISTILL this into:"
        "\n• TITLE: A specific, actionable name (max 6 words) that captures the concrete styling concept. AVOID generic words like 'style', 'fashion', 'look', 'outfit', 'trend'. Use specific descriptors, materials, silhouettes, moods, or techniques instead."
        "\n• DESCRIPTION: A concise explanation (1-2 sentences) of why this trend matters and how to style it"
    )

    # Format outfit items for analysis
    items_desc = []
    for item in outfit_items:
        item_type = item.get("type", "")
        keywords = item.get("keywords", "")
        if item_type and keywords:
            items_desc.append(f"{item_type}: {keywords}")
    
    outfit_description = "; ".join(items_desc) if items_desc else "no items specified"

    if source_img_url:
        # Include vision analysis when image is provided
        return [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"GENDER CONTEXT: {gender}\n\nCURRENT DATE: {date_iso}\n\nOUTFIT ITEMS TO ANALYZE:\n{outfit_description}\n\nStudy the reference image to understand the visual vibe and styling direction. Use both the item descriptions and visual analysis to identify the core trend concept.\n\nOUTPUT: Return a JSON object with keys 'title' and 'description' that distill the core trend concept."},
                    {"type": "image_url", "image_url": {"url": source_img_url}},
                ],
            },
        ]
    else:
        # Text-only analysis when no image is provided
        return (
            instructions
            + "\n\nGENDER CONTEXT:\n"
            + gender
            + "\n\nCURRENT DATE:\n"
            + date_iso
            + "\n\nOUTFIT ITEMS TO ANALYZE:\n"
            + outfit_description
            + "\n\nOUTPUT: Return a JSON object with keys 'title' and 'description' that distill the core trend concept."
        )


def build_trend_outfit_variation_prompt(
    *,
    gender: str,
    explore_title: str,
    explore_description: str,
    base_outfit_items: List[Dict[str, str]],
    desired_count: int,
    previous_outfit_variations: List[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """Prompt messages for creating additional trend outfit variations tied to an explore idea."""

    user_message = (
        "Create polished, trend-forward outfit variations that expand on the same explore idea.\n"
        "Focus on keeping the styling direction cohesive with the explore idea while ensuring each variation feels new and distinct.\n"
        "Return the outfits using the provided JSON schema function-call format.\n\n"

        f"DESIRED VARIATIONS: {desired_count}\n"
        f"GENDER CONTEXT: {gender or 'unspecified'}\n"
        f"EXPLORE IDEA TITLE: {explore_title.strip()}\n"
        f"EXPLORE IDEA DESCRIPTION: {explore_description.strip()}\n"
    )

    # Collect all existing outfits (base + previous variations)
    all_existing_outfits = []
    
    # Add base outfit items
    if base_outfit_items:
        formatted_items = []
        for item in base_outfit_items:
            item_type = (item or {}).get("type", "").strip()
            keywords = (item or {}).get("keywords", "").strip()
            if item_type and keywords:
                formatted_items.append(f"- {item_type}: {keywords}")
        if formatted_items:
            all_existing_outfits.append(formatted_items)

    # Add previous variations
    if previous_outfit_variations:
        for variation in previous_outfit_variations:
            variation_items = variation.get("trend_outfit_items", variation.get("items", []))
            if variation_items:
                formatted_variation_items = []
                for item in variation_items[:3]:  # Limit to first 3 items to avoid overly long prompts
                    item_type = (item or {}).get("type", "").strip()
                    keywords = (item or {}).get("keywords", "").strip()
                    if item_type and keywords:
                        formatted_variation_items.append(f"- {item_type}: {keywords}")
                if formatted_variation_items:
                    all_existing_outfits.append(formatted_variation_items)

    # Add existing outfits section if any exist
    if all_existing_outfits:
        user_message += "\nEXISTING OUTFITS (avoid creating similar outfits):\n"
        for i, outfit_items in enumerate(all_existing_outfits, 1):
            user_message += f"Outfit {i}: {', '.join(outfit_items)}\n"
        user_message += "\n"

    user_message += (
        "Requirements:\n"
        "- Invent outfits that clearly align with the explore idea's theme.\n"
        "- Keep items realistic, wearable, and shoppable.\n"
        "- Avoid reusing the exact keywords from existing outfits; evolve them thoughtfully.\n"
        "- Ensure each outfit has unique item keywords with sensible color, material, and fit descriptors.\n"
        "- Do not include any metadata such as source IDs or image URLs.\n"
        "- Try to be as creative as possible and come up with FRESH and TRENDY and UNIQUE outfits and ideas, not just variations of the same outfits.\n"
        "- If existing outfits are provided, avoid creating outfits that are too similar to them."
    )

    system_message = (
        "You are an expert fashion stylist generating structured outfit recommendations. "
        "Respond ONLY with the function call dictated by the provided schema. "
        "Each outfit must contain cohesive items that suit the specified gender context."
    )

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]


def build_trend_outfit_analysis_messages(
    *,
    image_url: str,
) -> List[Dict[str, Any]]:
    """Prompt messages for extracting structured outfit data from an image reference."""

    clothing_types = ", ".join(config.CLOTHING_ITEMS)

    system_message = (
        "You are a meticulous fashion data analyst. "
        "Your job is to translate reference imagery into structured outfit metadata. "
        "Always respond using the provided JSON schema only. "
        "Focus on the dominant clothing pieces that define the styling direction."
    )

    user_instructions = (
        "Study the reference image and extract ONE coherent outfit representation.\n"
        "First, determine if this image shows a valid, complete outfit that would be suitable for trend analysis.\n"
        "If the image does NOT show a clear, complete outfit (e.g., it's a product shot, accessory-only, unclear image, or not fashion-related), "
        "return: {\"not_valid_outfit\": true}\n"
        "Otherwise, return exactly one outfit object in the schema.\n\n"
        "Rules for valid outfits:\n"
        "- Capture the 3-5 most essential items (outerwear, dresses count as single layers).\n"
        "- Item.type must be chosen from: "
        + clothing_types
        + "\n- Item.keywords must be a single space-delimited search phrase.\n"
        "- Begin keywords with the appropriate gender prefix ('mens' or 'womens').\n"
        "- Include color (e.g., color:navy) and key material or fit descriptors when visible.\n"
        "- Avoid commas, brand names, or vague adjectives.\n"
        "- If an item category is not clearly visible, omit it rather than guessing.\n"
        "- Determine the gender context from the image and include it in the response.\n\n"
        "Also provide a concise outfit name (3-5 words) that summarizes the look."
    )

    return [
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_instructions},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]
