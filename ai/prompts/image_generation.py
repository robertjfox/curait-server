import json
from typing import List, Dict, Any, Optional


# Toggle for background rendering in flatlay images
USE_CONTEXTUAL_BACKGROUNDS = True


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
    
    separator_instruction = (
        "Keep a bold red line between each cell."
        if len(outfits) > 1
        else "Do not include any red divider line or cell separator."
    )

    # Combine all outfits into a single prompt
    combined_prompt = f"""
    Dress the avatars in the following outfits from left to right.
    {background_instruction}
    Keep each avatars body proportions EXACTLY as they are now, do not increase the height.
    You may slightly change the body positioning to give a bit of movement, like in a model photoshoot.
    The vibe of the clothing should be realistic and trendy, like a pinterest post. Think FASHION.
    The user should be looking directly at the camera. KEEP A HIGH FIDELITY OF THE USER'S FACE. CLOSED MOUTH. MODEL GAZE.
    Never roll, cuff, scrunch, or push up shirt sleeves or overshirt sleeves. Sleeves should hang naturally at their intended length.
    {separator_instruction}
    NEVER include any text in the image.
    """
    
    # Add outfit details
    for i, outfit in enumerate(outfits):
        combined_prompt += f"Outfit {i+1}:\n{json.dumps(outfit, ensure_ascii=False)}\n\n"
    
    return combined_prompt


def create_virtual_tryon_prompt() -> str:
    """Create a prompt for virtual try-on generation."""
    return (
        "Use the first image (user model) as base. Use the second image (clothing grid) to dress them. "
        "Same size, no text. Never roll, cuff, scrunch, or push up shirt sleeves or overshirt sleeves; "
        "sleeves should hang naturally at their intended length."
    ) 


def create_fullbody_avatar_prompt(
    *,
    height_cm: Optional[float] = None,
    weight_kg: Optional[float] = None,
    gender: Optional[str] = None,
) -> str:
    """Prompt for generating a studio full-body avatar from a selfie.

    The first image input is the user's selfie. Output should be a full-body,
    front-facing studio shot on a clean white background in the exact pose
    described, preserving the user's facial identity.
    """
    metrics = []
    if height_cm is not None:
        metrics.append(f"height ≈ {int(round(height_cm))} cm")
    if weight_kg is not None:
        metrics.append(f"weight ≈ {int(round(weight_kg))} kg")
    metrics_text = (" (" + ", ".join(metrics) + ")") if metrics else ""
    gender_text = f" Present as a {gender.lower()} model silhouette." if gender else ""

    return (
        "Use the first image as the binding identity reference for the user's face, hair, skin tone, and facial structure. "
        "Generate a photorealistic FULL-BODY studio avatar of the same person standing front-facing in a neutral stance, "
        "feet hip-width apart, arms relaxed at sides, closed mouth, calm model gaze. "
        "Do not beautify into a different person. Preserve face shape, eyes, nose, mouth, jaw, hairline, hairstyle, complexion, "
        "and overall identity from the selfie with very high fidelity. Minor grooming cleanup is allowed only if identity is unchanged. "
        f"Match the user's real body scale and proportions as closely as possible{metrics_text}; height is especially important. "
        "Do not make the person taller, shorter, thinner, heavier, more muscular, or more stylized than the provided measurements and selfie imply. "
        f"{gender_text} "
        "Plain seamless white background, even soft lighting, natural skin tones, no hard shadows, no text, no logos. "
        "Camera: full-length portrait, subject centered, include head to shoes with small margin. "
        "Use a 3:4 portrait composition with comfortable horizontal breathing room on both sides of the body. "
        "Wardrobe: plain white crew-neck t-shirt, basic straight-leg khaki chino pants at full length, clean white low-top sneakers, no logos. "
        "Do not use shorts. Do not crop off feet or head. Output a single final image only."
    )