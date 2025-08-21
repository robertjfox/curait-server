import json
from typing import List, Dict, Any, Optional


def PRODUCT_REFERENCE_MODE() -> str:
    return """
    PRODUCT REFERENCE MODE:
    - A 2x2 grid of product images is provided as visual reference, with the users face in the center
    - Each cell in the grid shows a clothing item to incorporate into the outfit
    - Read the description above each grid cell to understand the clothing item
    - ONLY take the specified clothing item from the description, for example, if its the description is for a white shirt, but it shoes a tie - you should only use the white shirt, not the tie
    - Match the colors, patterns, and styles shown in each grid cell precisely
    - Use all items from the grid to create a cohesive complete outfit
    - Ensure the clothing items look like the specific products shown in the grid

    - IMPORTANT: There is a circular overlay in the center of the grid showing the user's face - this is the target person who should be wearing the outfit. Use this face as your primary reference for:
      * Facial features (eyes, nose, mouth, jawline, etc.)
      * Hair color and style
      * PLEASE USE THE HAIRSTYLE FROM THE CENTER FACE IMAGE
      * Skin tone and complexion
      * Overall head shape and proportions
      * Age and gender characteristics

    - Create a realistic person with this exact face wearing all the clothing items from the grid
    - Do not reference any of the physical attributes of the people in the product grid cells (only use them for clothing reference)
    """


def generate_virtual_tryon_prompt(
    gender: str = "female",
    user_data: Optional[Dict[str, Any]] = None,
) -> str:
    
    gender_desc = "woman" if gender.lower() == "female" else "man"
    
    user_context_section = ""

    if user_data and isinstance(user_data, dict):
        ctx = user_data.get("context") or {}
        body_ctx = ctx.get("body_context", {})

        user_context_section = f"""
        BODY SHAPE CONTEXT:
        {json.dumps(body_ctx, indent=2)}
        """
    

    
    # Always use product reference mode since products are required
    mode_guidance = PRODUCT_REFERENCE_MODE()

    return f"""
    A {gender_desc} model wearing a complete outfit consisting of the clothing items shown in the product grid
    {user_context_section}
    {mode_guidance}

    MODEL & COMPOSITION:
    - Full body shot showing entire outfit from head to toe
    - Model positioned in CENTER of square image frame
    - Head at approximately 1/4 down from top (leave 25% space above)
    - Shoes must be visible within frame. USE THE EXACT SHOES FROM THE INPUT IMAGE AS BEST AS YOU POSSIBLY CAN.
    - Attractive, confident pose with front-facing face
    - Analyze their height and weight to generate the models body type, but be very flattering to their body type
    - High fashion, editorial quality with excellent lighting

    BACKGROUND & SETTING:
    - Subtle background setting and lighting influenced by the user context
    - No text or other people

    """


