import json
from typing import List, Dict, Any


# Toggle for background rendering in flatlay images
USE_CONTEXTUAL_BACKGROUNDS = False


def create_flatlay_prompt(outfits: List[Dict[str, Any]]) -> str:
    """Create a prompt for flatlay image generation with multiple outfits."""
    
    
    # Background-specific instructions
    if USE_CONTEXTUAL_BACKGROUNDS:
        background_instruction = """
        And provide individual background that fits the vibe of each outfit and is not distracting.
        The background should a scene that the user fits into naturally, not something that is contrived or abstract.
        Do not make the background or the lighting of the image too dark or too light.
        """
    else:
        background_instruction = "Use a clean, all white background for each outfit."
    
    # Combine all outfits into a single prompt
    combined_prompt = f"""
    Dress the avatars in the following outfits from left to right.
    {background_instruction}
    Keep each avatars body proportions EXACTLY as they are now, do not increase the height.
    You may slightly change the body positioning to give a bit of movement, like in a model photoshoot.
    The user should be looking directly at the camera. KEEP A HIGH FIDELITY OF THE USER'S FACE.
    Keep a bold red line between each cell.
    NEVER include any text in the image.
    """
    
    # Add outfit details
    for i, outfit in enumerate(outfits):
        combined_prompt += f"Outfit {i+1}:\n{json.dumps(outfit, ensure_ascii=False)}\n\n"
    
    return combined_prompt


def create_virtual_tryon_prompt() -> str:
    """Create a prompt for virtual try-on generation."""
    return "Use the first image (user model) as base. Use the second image (clothing grid) to dress them. Same size, no text." 