from typing import Dict, Any, List


def generate_outfit_modification_prompt(
    current_outfit_items: List[Dict[str, Any]],
    user_message: str,
    user_gender: str = None
) -> str:
    """Generate a prompt for analyzing which items to modify in an outfit based on user feedback."""
    
    gender_context = ""
    if user_gender:
        gender_context = f"Generate keywords appropriate for {user_gender.lower()}'s fashion."
    
    # Build current outfit context
    outfit_context = "CURRENT OUTFIT:\n"
    for item in current_outfit_items:
        outfit_context += f"- {item['type']}: {item['title']} (Keywords: {item.get('keywords', 'N/A')})\n"
    
    prompt = f"""You are a fashion stylist assistant. A user wants to modify their current outfit based on their feedback.

{outfit_context}

USER FEEDBACK: "{user_message}"

YOUR TASK:
Analyze the user's feedback and determine which items (if any) need to be modified, then generate new search keywords for those items.

ANALYSIS RULES:
- Look for specific item mentions: "shirt", "pants", "shoes", "sunglasses", "shades", etc.
- Look for color changes: "make it blue", "change to red", "different color"
- Look for material changes: "make it leather", "suede", "cotton"
- Look for style changes: "printed", "solid", "striped"
- If no specific item is mentioned, infer from context (e.g., "make it blue" might refer to the most prominent item)

KEYWORD REQUIREMENTS:
- Include: garment noun, fit, color, material, pattern/texture
- Add type-specific attributes based on the item type
- Include season/weather context if relevant
- NO price symbols, quotes, or commas - use spaces only
- Keep to ~9-12 tokens, natural query style
- Avoid brand names unless specifically requested

{gender_context}

Return ONLY the items that need modification with their new keywords. If no modifications are needed, return an empty array."""

    return prompt 