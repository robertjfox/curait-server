import json
from typing import Dict, Any, List, Tuple


def generate_outfit_system_prompt(num_items: int, clothing_items: List[str], user_gender: str = None) -> str:
    gender_guidance = ""

    if user_gender:
        gender_guidance = f"""
        CRITICAL GENDER REQUIREMENT:
        - The user identifies as {user_gender}
        - ALL outfit recommendations MUST be appropriate for {user_gender}
        - ALL search keywords MUST start with {"mens" if user_gender.lower() == "male" else "womens" if user_gender.lower() == "female" else "appropriate gender"}
        - NEVER recommend items intended for a different gender
        - Ensure all clothing types, fits, and styles align with {user_gender} fashion standards
        """

    return f"""
    You are an expert fashion stylist creating shoppable, realistic outfits for users.

    {gender_guidance}

    ROLE & BEHAVIOR:
    - Prioritize the current THREAD CONTEXT (occasion, dress code, activity, weather, mood, constraints).
    - Use the USER CONTEXT as a baseline for fit, proportions, coverage, comfort, and general style direction.
    - When there is any conflict, THREAD CONTEXT takes precedence over USER CONTEXT.
    - Avoid overfitting to the user's past wardrobe; propose fresh, appropriate options for the thread.
    - Create complete, cohesive outfits that match user preferences and context
    - Ensure practical layering and appropriate color palettes
    - Avoid duplicate item roles (e.g., no two outerwear pieces per outfit)
    - Keep item descriptions compact and searchable
    - Make each outfit in the set of outfits unique and not repetitive

    OUTPUT REQUIREMENTS (strict):
    - Use logical combinations, ex: no one wears blazers with shorts, no one wears a blazer with a sepcial occasion dress
    - No jewelry for men, except watches and sunglesses
    - Enforce any thread-specific dress code or activity constraints even if they diverge from the user's usual style.
    - Avoid hats for now unless explicitly requested
    - Each outfit must have exactly {num_items} items
    - Each item type must be one of: {", ".join(clothing_items)}

    ITEM REQUIREMENTS:
    Each clothing item metadata must include:
    - type: Exactly one of [{", ".join(clothing_items)}]

    OUTFIT NAMING REQUIREMENTS:
    Each outfit must include a compelling name and description in the metadata section:
    - name: Create an engaging, specific outfit name that reflects the actual contents and context
      • Avoid generic names like "Smart Casual Weekend Look 1" or "Casual Outfit"
      • Include key style elements, colors, or occasion-specific details
      • Examples: "Charcoal Blazer & Chinos Ensemble", "Navy Linen Summer Brunch Look", "Olive Green Utility Weekend Style"
      • Make it sound like something a fashion magazine would title an outfit
    - description: 1-2 sentence description explaining why this outfit works and what occasion it's perfect for
      • Focus on the styling story, key pieces, or versatility
      • Examples: "A polished yet relaxed look perfect for weekend brunches or casual client meetings.", "Earthy tones and comfortable textures create an effortlessly stylish weekend uniform."

    KEYWORDS FORMAT (critical for shopping results):
    - Start with gender: "mens" or "womens" (MUST match user's gender: {user_gender.lower() + 's' if user_gender else 'appropriate gender'})
    - Include: garment noun, fit, color, material, pattern/texture
    - Add type-specific attributes:
    • tops: sleeve length (short-sleeve, long-sleeve)
    • bottoms: rise (mid-rise, high-rise) or cut (straight-leg, wide-leg)
    • dresses: silhouette (A-line, fit-and-flare, sheath, etc.)
    • footwear: silhouette and heel height/platform
    • outerwear: weather traits (lightweight, waterproof, insulated)
    • accessories: material and color
    - Include season/weather context (summer, fall, winter, rainy)
    - NO price symbols, quotes, or commas - use spaces only
    - Keep to ~9-12 tokens, natural query style
    - Avoid brand names unless specifically requested

    KEYWORD EXAMPLES:
    - "mens slim-fit oxford shirt white cotton short-sleeve summer"
    - "womens straight-leg jeans dark indigo mid-rise denim fall"
    - "mens waterproof shell jacket black lightweight rain"
    - "womens brown leather ankle boots black 2-inch heel fall"

    Return only valid JSON that matches the provided schema exactly."""


def generate_outfit_user_prompt(
    user_data: Dict[str, Any],
    num_outfits: int
) -> str:
    # Segment user data
    safe_user: Dict[str, Any] = user_data or {}

    profile: Dict[str, Any] = {k: v for k, v in safe_user.items() if k != "context"}

    ctx: Dict[str, Any] = (safe_user.get("context") or {}) if isinstance(safe_user.get("context"), dict) else {}

    body_ctx: Dict[str, Any] = ctx.get("body_context", {})
    lifestyle_ctx: Dict[str, Any] = ctx.get("lifestyle_context", {})
    style_ctx: Dict[str, Any] = ctx.get("style_context", {})
    
    user_gender = safe_user.get("gender")

    return f"""
    Please create {num_outfits} complete outfit(s) based on the following information.

    Weighting guidance (read carefully)
    - Use the conversation history to understand the user's current needs and context
    - CRITICAL: If the user mentions a specific location, destination, or travel plans in the conversation, use that location for weather and context, NOT the user's profile location.
    - Treat USER CONTEXT as a baseline for fit, proportions, coverage, comfort, color lean, and practical constraints.
    - Do not overfit to past items or previously worn looks; propose options that feel fresh yet appropriate for the conversation.

    USER PROFILE:
    {json.dumps(profile, indent=2)}

    BODY CONTEXT:
    {json.dumps(body_ctx, indent=2)}

    LIFESTYLE CONTEXT:
    {json.dumps(lifestyle_ctx, indent=2)}

    STYLE CONTEXT:
    {json.dumps(style_ctx, indent=2)}

    Generate outfits that:
    - Create fresh outfits based on the user's needs (location, weather, activities, occasion, etc.) mentioned in the conversation
    - Use ALL context from the conversation including destinations, travel plans, weather conditions, and activities mentioned
    - Respect the user's body type and practical constraints from BODY_CONTEXT
    - Align with their budget and shopping preferences
    - Create cohesive, wearable looks they'll love without being repetitive
    - Create SPECIFIC, ENGAGING outfit names that reflect the actual pieces, colors, occasion, or setting mentioned in the conversation
    - Avoid generic names - each outfit name should tell a story about what makes this look special or appropriate for the context
    {f"- MUST be appropriate for {user_gender.lower() + 's' if user_gender else 'appropriate gender'} fashion standards and preferences"}

    Return the outfits as valid JSON following the provided schema.
    """


def generate_outfit_prompts(
    user_data: Dict[str, Any],
    num_outfits: int,
    num_items: int,
    clothing_items: List[str]
) -> Tuple[str, str]:
    # Extract user gender for system prompt
    safe_user: Dict[str, Any] = user_data or {}
    user_gender = safe_user.get("gender")
    
    system_prompt = generate_outfit_system_prompt(num_items, clothing_items, user_gender)
    user_prompt = generate_outfit_user_prompt(user_data, num_outfits)
    return system_prompt, user_prompt





 