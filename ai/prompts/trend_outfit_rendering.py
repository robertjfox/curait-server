from typing import List, Dict, Any


def build_trend_outfit_rendering_prompt(*, title: str, description: str, gender: str, outfit_items: List[Dict[str, str]]) -> str:
    """Prompt for generating a 3:4 trend outfit rendering image that visually conveys the outfit.

    The prompt biases toward clean, high‑impact editorial design suitable for a fashion app display.
    """
    # Format outfit items into a readable description
    items_desc = []
    for item in outfit_items:
        item_type = item.get("type", "")
        keywords = item.get("keywords", "")
        if item_type and keywords:
            items_desc.append(f"{item_type}: {keywords}")
    
    outfit_description = "; ".join(items_desc) if items_desc else "casual outfit"
    
    return (
        "IMPORTANT: The image should be in a [3:4] width/height aspect ratio. (Portrait)"
        "Create a polished, brand‑neutral fashion rendering image showing the trend outfit. "
        "Show the full body of the person, including the legs and feet"
        "Focus on fashion styling and body language that conveys the trend concept. "
        "Use a subtle and relevant background setting that matches the theme and concept described. "
        "No watermarks, no logos, no text elements, no captions or decorative overlays. "
        "Use crisp & clear coloring, studio‑grade lighting."

        + "\n\nTITLE: " + title.strip()
        + "\nDESCRIPTION: " + description.strip()
        + "\nGENDER CONTEXT: " + gender.strip()
        + "\nOUTFIT: " + outfit_description
    )
